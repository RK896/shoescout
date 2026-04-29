"""
Dick's Sporting Goods API-based scraper.

Uses the reverse-engineered prod-catalog-product-api endpoint that returns
clean JSON with product data, prices, and attributes. Much faster and more
reliable than browser automation.

API endpoint:
    GET https://prod-catalog-product-api.dickssportinggoods.com/v2/search?searchVO={JSON}

Response includes:
    - productVOs: list of products with name, brand, SEO URL, thumbnail
    - productDetails: dict keyed by catentryId with prices and attributes
"""
import json
import re
import time
import urllib.parse
from dataclasses import dataclass
from typing import Optional

import requests


@dataclass
class DicksProduct:
    """Represents a scraped Dick's Sporting Goods product."""
    brand: str
    model: str
    price: str
    list_price: str
    image: str
    link: str
    gender: str
    retailer: str = "Dick's Sporting Goods"

    def to_dict(self) -> dict:
        return {
            "brand": self.brand,
            "model": self.model,
            "price": self.price,
            "image": self.image,
            "link": self.link,
            "retailer": self.retailer,
        }


# Required headers for the API
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Origin": "https://www.dickssportinggoods.com",
    "Referer": "https://www.dickssportinggoods.com/",
    "channel": "dsg",
    "x-dsg-platform": "v2",
    "pool-c-swimlane": "71",
    "disable-pinning": "false",
    "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
}

BASE_URL = "https://prod-catalog-product-api.dickssportinggoods.com/v2/search"
DSG_BASE = "https://www.dickssportinggoods.com"
IMAGE_BASE = "https://dks.scene7.com/is/image/GolfGalaxy"

# NFL/NCAA team names to filter out
TEAM_NAMES = {
    # NFL teams
    "cowboys", "chiefs", "eagles", "patriots", "packers", "49ers", "niners",
    "ravens", "bills", "bengals", "browns", "broncos", "texans", "colts",
    "jaguars", "chargers", "raiders", "dolphins", "vikings", "saints",
    "giants", "jets", "steelers", "seahawks", "buccaneers", "bucs",
    "titans", "commanders", "bears", "lions", "falcons", "panthers",
    "cardinals", "rams",
    # Common college teams
    "crimson tide", "bulldogs", "tigers", "wolverines", "buckeyes",
    "longhorns", "sooners", "gators", "seminoles", "hurricanes",
    "tar heels", "duke", "wildcats", "trojans", "bruins", "ducks",
    # Generic team indicators
    "nfl", "ncaa", "college", "team edition",
}

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
    "hoka gaviota 5",
    # Brooks
    "brooks ghost 16",
    "brooks ghost 15",
    "brooks glycerin 21",
    "brooks glycerin 20",
    "brooks adrenaline gts 24",
    "brooks adrenaline gts 23",
    "brooks launch 10",
    # ASICS
    "asics gel nimbus 26",
    "asics gel nimbus 25",
    "asics gel kayano 31",
    "asics gel kayano 30",
    "asics gt 2000 12",
    "asics novablast 4",
    # New Balance
    "new balance fresh foam 1080",
    "new balance fresh foam 880",
    "new balance fuelcell rebel",
    "new balance fuelcell propel",
    # Saucony
    "saucony ride 17",
    "saucony ride 16",
    "saucony guide 17",
    "saucony triumph 22",
    "saucony kinvara 14",
    # Adidas
    "adidas ultraboost",
    "adidas supernova",
    "adidas solarglide",
    # On
    "on cloudmonster",
    "on cloudrunner",
    "on cloudsurfer",
    "on cloudflow",
]


def _is_team_edition(name: str, attributes_str: str) -> bool:
    """
    Check if a product is an NFL/NCAA team edition.

    Args:
        name: Product name
        attributes_str: JSON string of attributes from productVOs

    Returns:
        True if this is a team edition product to filter out
    """
    name_lower = name.lower()

    # Check for team names in product name
    for team in TEAM_NAMES:
        if team in name_lower:
            return True

    # Check for NCAA/NFL attribute keys
    if attributes_str:
        try:
            attrs = json.loads(attributes_str)
            for attr in attrs:
                # Key "4423" indicates NCAA products
                if "4423" in attr:
                    return True
                # Look for NFL attribute
                if "NFL" in str(attr.values()):
                    return True
        except (json.JSONDecodeError, TypeError):
            pass

    return False


def _extract_gender(attributes_str: str) -> Optional[str]:
    """
    Extract gender from attributes JSON string.

    The gender is stored with key "5495" in the attributes array.
    Values: "Men's", "Women's", "Kids'", "Unisex"

    Returns:
        "Men's", "Women's", or None if not found/invalid
    """
    if not attributes_str:
        return None

    try:
        attrs = json.loads(attributes_str)
        for attr in attrs:
            if "5495" in attr:
                gender = attr["5495"]
                if gender in ("Men's", "Women's"):
                    return gender
    except (json.JSONDecodeError, TypeError):
        pass

    return None


def _clean_model_name(name: str, brand: str) -> str:
    """
    Clean up the product name to get a standardized model name.

    Removes brand prefix, gender suffix, and "Running Shoes" suffix.
    """
    model = name

    # Remove brand prefix if present
    if brand and model.lower().startswith(brand.lower()):
        model = model[len(brand):].strip()

    # Remove common suffixes
    suffixes_to_remove = [
        " Running Shoes",
        " Running Shoe",
        " Shoes",
        " Shoe",
    ]
    for suffix in suffixes_to_remove:
        if model.endswith(suffix):
            model = model[:-len(suffix)]

    # Remove gender from model name (Men's, Women's, etc.)
    model = re.sub(r"\b(Men's|Women's|Mens|Womens|Men|Women)\b", "", model, flags=re.IGNORECASE)

    # Clean up extra whitespace
    model = " ".join(model.split())

    return model.strip()


def search_dsg(search_term: str, page: int = 0, page_size: int = 48) -> dict:
    """
    Search Dick's Sporting Goods API for products.

    Args:
        search_term: Search query (e.g., "nike pegasus 41")
        page: Page number (0-indexed)
        page_size: Number of results per page (max 48)

    Returns:
        Raw API response as dict, or empty dict on error
    """
    search_vo = {
        "pageNumber": page,
        "pageSize": page_size,
        "selectedSort": 0,
        "selectedStore": "105",
        "storeId": "15108",
        "zipcode": "08540",
        "isFamilyPage": False,
        "mlBypass": False,
        "searchTerm": search_term,
    }

    # URL encode the searchVO JSON
    encoded_vo = urllib.parse.quote(json.dumps(search_vo))
    url = f"{BASE_URL}?searchVO={encoded_vo}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error searching DSG for '{search_term}': {e}")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error parsing DSG response for '{search_term}': {e}")
        return {}


def parse_dsg_response(response: dict) -> list[DicksProduct]:
    """
    Parse the DSG API response and extract products.

    Joins productVOs with productDetails using catentryId as key.
    Filters out team editions and non-running shoes.

    Returns:
        List of DicksProduct objects
    """
    products = []

    product_vos = response.get("productVOs", [])
    product_details = response.get("productDetails", {})

    for vo in product_vos:
        try:
            cat_entry_id = str(vo.get("catentryId", ""))
            name = vo.get("name", "")
            brand = vo.get("mfName", "")
            attributes_str = vo.get("attributes", "")
            seo_url = vo.get("dsgSeoUrl", "")
            thumbnail = vo.get("thumbnail", "")

            # Skip if missing essential data
            if not name or not brand or not cat_entry_id:
                continue

            # Filter out team editions
            if _is_team_edition(name, attributes_str):
                continue

            # Extract and filter by gender (skip Kids)
            gender = _extract_gender(attributes_str)
            if not gender:
                continue

            # Get price details
            details = product_details.get(cat_entry_id, {})
            prices = details.get("prices", {})

            # Use minofferprice (sale/current price)
            offer_price = prices.get("minofferprice", "")
            list_price = prices.get("minlistprice", "")

            if not offer_price:
                continue

            # Format prices
            try:
                price_str = f"${float(offer_price):.2f}"
                list_price_str = f"${float(list_price):.2f}" if list_price else price_str
            except ValueError:
                continue

            # Build URLs
            link = f"{DSG_BASE}{seo_url}" if seo_url else ""
            image_url = f"{IMAGE_BASE}/{thumbnail}?wid=500&hei=500&fmt=pjpeg" if thumbnail else ""

            # Clean up model name
            model = _clean_model_name(name, brand)

            # Add brand prefix back for consistency with other scrapers
            full_model = f"{brand} {model}" if not model.lower().startswith(brand.lower()) else model

            products.append(DicksProduct(
                brand=brand,
                model=full_model,
                price=price_str,
                list_price=list_price_str,
                image=image_url,
                link=link,
                gender=gender,
            ))

        except Exception as e:
            print(f"Error parsing DSG product: {e}")
            continue

    return products


def scrape_dsg_all(max_pages: int = 20) -> list[DicksProduct]:
    """
    Scrape ALL running shoes from Dick's using broad search with pagination.

    This is the preferred method - gets ~600+ products by searching "running shoes"
    and paginating through all results. No need to maintain a list of shoe models.

    Args:
        max_pages: Maximum number of pages to fetch (default 20, ~960 products max)

    Returns:
        List of DicksProduct objects, deduplicated by model name
    """
    all_products: dict[str, DicksProduct] = {}  # Dedupe by model
    page = 0
    page_size = 48

    print("Scraping all running shoes from Dick's...")

    while page < max_pages:
        print(f"  Fetching page {page + 1}...")
        response = search_dsg("running shoes", page=page, page_size=page_size)

        if not response:
            print(f"  No response on page {page}, stopping")
            break

        total_count = response.get("totalCount", 0)
        product_vos = response.get("productVOs", [])

        if not product_vos:
            print(f"  No products on page {page}, stopping")
            break

        products = parse_dsg_response(response)
        print(f"  Page {page + 1}: {len(products)} products (total available: {total_count})")

        # Add to dict, keeping lowest price per model
        for product in products:
            key = product.model.lower()
            if key not in all_products:
                all_products[key] = product
            else:
                # Keep the one with lower price
                try:
                    existing_price = float(all_products[key].price.replace("$", ""))
                    new_price = float(product.price.replace("$", ""))
                    if new_price < existing_price:
                        all_products[key] = product
                except ValueError:
                    pass

        # Check if we've fetched all products
        if (page + 1) * page_size >= total_count:
            print(f"  Reached end of results")
            break

        page += 1
        time.sleep(1.0)  # Polite delay between pages

    print(f"Scraped {len(all_products)} unique models from {page + 1} pages")
    return list(all_products.values())


def scrape_dsg_shoes(shoe_list: Optional[list[str]] = None) -> list[DicksProduct]:
    """
    Scrape Dick's for a list of running shoe models (search-based approach).

    Use scrape_dsg_all() instead for comprehensive scraping without maintaining
    a list of shoe models.

    Args:
        shoe_list: List of search terms (e.g., ["nike pegasus 41", "hoka clifton 9"])
                   If None, uses POPULAR_RUNNING_SHOES

    Returns:
        List of DicksProduct objects, deduplicated by model name
    """
    if shoe_list is None:
        shoe_list = POPULAR_RUNNING_SHOES

    all_products: dict[str, DicksProduct] = {}  # Dedupe by model

    for i, search_term in enumerate(shoe_list):
        print(f"Searching DSG for: {search_term} ({i+1}/{len(shoe_list)})")

        response = search_dsg(search_term)
        if not response:
            continue

        products = parse_dsg_response(response)
        print(f"  Found {len(products)} products")

        # Add to dict, keeping lowest price per model
        for product in products:
            key = product.model.lower()
            if key not in all_products:
                all_products[key] = product
            else:
                # Keep the one with lower price
                existing_price = float(all_products[key].price.replace("$", ""))
                new_price = float(product.price.replace("$", ""))
                if new_price < existing_price:
                    all_products[key] = product

        # Polite delay between requests
        if i < len(shoe_list) - 1:
            time.sleep(1.5)

    return list(all_products.values())


def scrape_dicks() -> list[dict]:
    """
    Main entry point matching existing scraper interface.

    Uses the full catalog browsing approach (scrape_dsg_all) to get ALL running
    shoes without needing to maintain a list of search terms.

    Returns list of shoe dicts compatible with existing add_shoes_to_db().
    """
    print("Scraping Dick's Sporting Goods...")
    products = scrape_dsg_all()
    print(f"Scraped {len(products)} unique shoes from Dick's")
    return [p.to_dict() for p in products]


if __name__ == "__main__":
    # Test run
    shoes = scrape_dicks()
    print(f"\nScraped {len(shoes)} shoes total")

    # Print sample
    for shoe in shoes[:10]:
        print(f"  {shoe['brand']} - {shoe['model']}: {shoe['price']}")
