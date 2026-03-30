"""
Zappos API-based scraper.

Uses the reverse-engineered janus/recos endpoint that returns recommendations
and search results with clean JSON data including price, brand, and product URLs.

API endpoint:
    GET https://www.zappos.com/directapi/janus/recos/get?filter=...&limit=50&txt={search}&widgets=search-1

The scraper automatically obtains fresh session cookies by visiting the Zappos
website, so no manual cookie refresh is needed.
"""
import re
import time
import urllib.parse
from dataclasses import dataclass
from typing import Optional

import requests


@dataclass
class ZapposProduct:
    """Represents a scraped Zappos product."""
    brand: str
    model: str
    price: str
    list_price: str
    image: str
    link: str
    gender: str
    category: str = "road"
    retailer: str = "Zappos"

    def to_dict(self) -> dict:
        return {
            "brand": self.brand,
            "model": self.model,
            "price": self.price,
            "image": self.image,
            "link": self.link,
            "gender": self.gender,
            "category": self.category,
            "retailer": self.retailer,
        }


# Global session - initialized lazily
_session: Optional[requests.Session] = None

BASE_URL = "https://www.zappos.com/directapi/janus/recos/get"


def _get_session() -> requests.Session:
    """
    Get or create a requests session with valid Zappos cookies.

    The session is initialized by visiting Zappos pages to obtain
    fresh session cookies automatically.
    """
    global _session

    if _session is not None:
        return _session

    print("Initializing Zappos session...")
    _session = requests.Session()
    _session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })

    # Visit main page and search page to get session cookies
    try:
        _session.get("https://www.zappos.com/", timeout=30)
        _session.get("https://www.zappos.com/running-shoes", timeout=30)
    except requests.RequestException as e:
        print(f"Warning: Failed to initialize Zappos session: {e}")

    # Get session-id from cookies
    session_id = _session.cookies.get("session-id", "")

    # Update headers for API requests
    _session.headers.update({
        "Accept": "application/json",
        "X-Mafia-Session-Id": session_id,
        "X-Mafia-Session-Token": "undefined",
        "X-Mafia-Auth-Requested": "true",
        "X-Mafia-Session-Requested": "true",
    })

    print(f"  Session initialized (session-id: {session_id[:20]}...)")
    return _session


def _reset_session() -> None:
    """Reset the session to force re-initialization on next request."""
    global _session
    _session = None

# Popular running shoe models to search for
POPULAR_RUNNING_SHOES = [
    # Nike
    "nike pegasus 41",
    "nike pegasus 40",
    "nike vomero 18",
    "nike infinity run 4",
    "nike invincible 3",
    "nike structure 25",
    "nike winflo 11",
    # HOKA
    "hoka clifton 9",
    "hoka clifton 10",
    "hoka bondi 8",
    "hoka bondi 9",
    "hoka mach 6",
    "hoka arahi 7",
    # Brooks
    "brooks ghost 16",
    "brooks ghost 15",
    "brooks glycerin 21",
    "brooks adrenaline gts 24",
    "brooks launch 10",
    # ASICS
    "asics gel nimbus 26",
    "asics gel kayano 31",
    "asics gt 2000 12",
    "asics novablast 4",
    # New Balance
    "new balance fresh foam 1080",
    "new balance fresh foam 880",
    "new balance fuelcell rebel",
    # Saucony
    "saucony ride 17",
    "saucony guide 17",
    "saucony triumph 22",
    "saucony kinvara 14",
    # Adidas
    "adidas ultraboost",
    "adidas supernova",
    # On
    "on cloudmonster",
    "on cloudrunner",
    "on cloudsurfer",
]


def _is_kids_shoe(name: str, brand: str) -> bool:
    """
    Check if a product is a kids shoe.

    Args:
        name: Product name
        brand: Brand name

    Returns:
        True if this is a kids shoe to filter out
    """
    name_lower = name.lower()
    brand_lower = brand.lower()

    kids_indicators = [
        "little kid",
        "big kid",
        "toddler",
        "infant",
        "kids'",
        "kids",
        "youth",
        "grade school",
        "preschool",
        "ps)",
        "gs)",
        "(td)",
    ]

    for indicator in kids_indicators:
        if indicator in name_lower or indicator in brand_lower:
            return True

    return False


    return "Unisex"


def _infer_gender(name: str, link: str) -> str:
    """
    Infer gender from product name or URL.
    Returns: "Men's", "Women's", or "Unisex"
    """
    name_lower = name.lower()
    link_lower = link.lower() if link else ""
    if "women" in name_lower or "woman" in name_lower:
        return "Women's"
    if "men" in name_lower and "women" not in name_lower:
        return "Men's"
    if "/women" in link_lower or "womens" in link_lower:
        return "Women's"
    if "/men" in link_lower or "mens" in link_lower:
        return "Men's"
    return "Unisex"


def _infer_category(name: str, link: str) -> str:
    """
    Infer if road or trail shoe from name or URL.
    Returns: "road" or "trail"
    """
    text = f"{name} {link}".lower()
    trail_keywords = ["trail", "mountain", "gravel", "terrex", "peregrine", "hierro", "cascadia", "speedcross", "wildhorse", "terra kiger"]
    for kw in trail_keywords:
        if kw in text:
            return "trail"
    return "road"


def _clean_model_name(name: str, brand: str) -> str:
    """
    Clean up the product name to get a standardized model name.

    Zappos names are usually clean like "Pegasus 41" without brand prefix.
    """
    model = name.strip()

    # If brand is not already in the name, prepend it
    if brand and not model.lower().startswith(brand.lower()):
        model = f"{brand} {model}"

    # Remove gender indicators from model name
    model = re.sub(r"\b(Men's|Women's|Mens|Womens|Men|Women)\b", "", model, flags=re.IGNORECASE)

    # Clean up extra whitespace
    model = " ".join(model.split())

    return model.strip()


def _parse_price(price_str: str) -> Optional[float]:
    """Parse a price string like '$96.81' to float."""
    if not price_str:
        return None
    cleaned = price_str.replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def search_zappos(search_term: str, limit: int = 50) -> dict:
    """
    Search Zappos API for products.

    Args:
        search_term: Search query (e.g., "nike pegasus 41")
        limit: Maximum number of results (default 50)

    Returns:
        Raw API response as dict, or empty dict on error
    """
    session = _get_session()

    # Build the filter parameter
    filter_param = 'z_cat_name_1 = "Shoes"'
    encoded_filter = urllib.parse.quote(filter_param)

    # Build the URL
    url = f"{BASE_URL}?filter={encoded_filter}&limit={limit}&txt={urllib.parse.quote(search_term)}&widgets=search-1"

    # Update referer for this specific search
    session.headers["Referer"] = f"https://www.zappos.com/search?term={urllib.parse.quote(search_term)}"

    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()

        # Check for empty response (session might have expired)
        if not response.text:
            print("Empty response - resetting session...")
            _reset_session()
            return {}

        return response.json()
    except requests.RequestException as e:
        print(f"Error searching Zappos for '{search_term}': {e}")
        _reset_session()  # Reset session on error
        return {}
    except ValueError as e:
        print(f"Error parsing Zappos response for '{search_term}': {e}")
        return {}


def parse_zappos_response(response: dict) -> list[ZapposProduct]:
    """
    Parse the Zappos API response and extract products.

    Args:
        response: Raw API response

    Returns:
        List of ZapposProduct objects
    """
    products = []

    # Get the search results from the response
    search_data = response.get("search-1", {})
    sims = search_data.get("sims", [])

    for item in sims:
        try:
            name = item.get("name", "")
            brand = item.get("brand", "")
            price_str = item.get("price", "")
            list_price_str = item.get("c_base_price", "")
            image = item.get("image_SQ", "")
            link = item.get("link", "")

            # Skip if missing essential data
            if not name or not brand:
                continue

            # Filter out kids shoes
            if _is_kids_shoe(name, brand):
                continue

            # Parse prices
            price = _parse_price(price_str)
            list_price = _parse_price(list_price_str)

            if price is None:
                continue

            # Format prices
            price_formatted = f"${price:.2f}"
            list_price_formatted = f"${list_price:.2f}" if list_price else price_formatted

            # Infer gender
            gender = _infer_gender(name, link)

            # Clean up model name
            model = _clean_model_name(name, brand)

            # Ensure link is absolute
            if link and not link.startswith("http"):
                link = f"https://www.zappos.com{link}"

            products.append(ZapposProduct(
                brand=brand,
                model=model,
                price=price_formatted,
                list_price=list_price_formatted,
                image=image,
                link=link,
                gender=gender,
                category=_infer_category(name, link),
                retailer=retailer,
            ))

        except Exception as e:
            print(f"Error parsing Zappos product: {e}")
            continue

    return products


def scrape_zappos_broad() -> list[ZapposProduct]:
    """
    Scrape Zappos using broad category searches to get maximum coverage.

    Unlike Dick's, Zappos doesn't have pagination on the janus endpoint.
    We use multiple broad searches (by brand) to maximize coverage.

    Returns:
        List of ZapposProduct objects, deduplicated by model name
    """
    # Broad search terms that return lots of running shoes
    broad_searches = [
        "running shoes",
        "nike running",
        "hoka running",
        "brooks running",
        "asics running",
        "new balance running",
        "saucony running",
        "adidas running",
        "on running shoes",
    ]

    all_products: dict[str, ZapposProduct] = {}  # Dedupe by model

    print("Scraping Zappos with broad searches...")
    for i, search_term in enumerate(broad_searches):
        print(f"  Searching: {search_term} ({i+1}/{len(broad_searches)})")

        response = search_zappos(search_term)
        if not response:
            continue

        products = parse_zappos_response(response)
        print(f"    Found {len(products)} products")

        # Add to dict, keeping lowest price per model
        for product in products:
            key = product.model.lower()
            if key not in all_products:
                all_products[key] = product
            else:
                existing_price = _parse_price(all_products[key].price) or float('inf')
                new_price = _parse_price(product.price) or float('inf')
                if new_price < existing_price:
                    all_products[key] = product

        time.sleep(1.0)

    print(f"Scraped {len(all_products)} unique models from Zappos")
    return list(all_products.values())


def scrape_zappos_shoes(shoe_list: Optional[list[str]] = None) -> list[ZapposProduct]:
    """
    Scrape Zappos for a list of running shoe models.

    For broader coverage without maintaining a list, use scrape_zappos_broad().

    Args:
        shoe_list: List of search terms (e.g., ["nike pegasus 41", "hoka clifton 9"])
                   If None, uses POPULAR_RUNNING_SHOES

    Returns:
        List of ZapposProduct objects, deduplicated by model name
    """
    if shoe_list is None:
        shoe_list = POPULAR_RUNNING_SHOES

    all_products: dict[str, ZapposProduct] = {}  # Dedupe by model

    for i, search_term in enumerate(shoe_list):
        print(f"Searching Zappos for: {search_term} ({i+1}/{len(shoe_list)})")

        response = search_zappos(search_term)
        if not response:
            continue

        products = parse_zappos_response(response)
        print(f"  Found {len(products)} products")

        # Add to dict, keeping lowest price per model
        for product in products:
            key = product.model.lower()
            if key not in all_products:
                all_products[key] = product
            else:
                # Keep the one with lower price
                existing_price = _parse_price(all_products[key].price) or float('inf')
                new_price = _parse_price(product.price) or float('inf')
                if new_price < existing_price:
                    all_products[key] = product

        # Polite delay between requests
        if i < len(shoe_list) - 1:
            time.sleep(1.5)

    return list(all_products.values())


def scrape_zappos() -> list[dict]:
    """
    Main entry point matching existing scraper interface.

    Uses the broad search approach to get maximum coverage without
    maintaining a list of specific shoe models.

    Returns list of shoe dicts compatible with existing add_shoes_to_db().
    """
    print("Scraping Zappos...")
    products = scrape_zappos_broad()
    print(f"Scraped {len(products)} unique shoes from Zappos")
    return [p.to_dict() for p in products]


if __name__ == "__main__":
    # Test run
    shoes = scrape_zappos()
    print(f"\nScraped {len(shoes)} shoes total")

    # Print sample
    for shoe in shoes[:10]:
        print(f"  {shoe['brand']} - {shoe['model']}: {shoe['price']}")
