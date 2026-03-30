"""
Road Runner Sports API-based scraper.

Uses direct HTTP requests to scrape the product catalog from Next.js data.
Product data is embedded in the __NEXT_DATA__ script tag on category pages.

The scraper fetches category pages and extracts product data from the
embedded JSON state, which is much faster than Selenium-based scraping.
"""
import json
import re
import time
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup


@dataclass
class RoadRunnerProduct:
    """Represents a scraped Road Runner Sports product."""
    brand: str
    model: str
    price: str
    list_price: str
    image: str
    link: str
    gender: str
    retailer: str = "Road Runner Sports"

    def to_dict(self) -> dict:
        return {
            "brand": self.brand,
            "model": self.model,
            "price": self.price,
            "image": self.image,
            "link": self.link,
            "retailer": self.retailer,
        }


# Global session - initialized lazily
_session: Optional[requests.Session] = None

BASE_URL = "https://www.roadrunnersports.com"

# Category URLs that return running shoes
# These are paginated - use pageNumber param for additional pages
CATEGORY_URLS = [
    "/category/Running+Shoes",  # All running shoes
]

# Known running shoe brands for filtering
RUNNING_BRANDS = {
    "nike", "brooks", "hoka", "saucony", "asics", "new balance",
    "adidas", "on", "mizuno", "altra", "salomon", "topo", "merrell",
    "karhu", "newton", "diadora", "361", "under armour"
}


def _get_session() -> requests.Session:
    """
    Get or create a requests session.
    """
    global _session

    if _session is not None:
        return _session

    print("Initializing Road Runner Sports session...")
    _session = requests.Session()
    _session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })

    print("  Session initialized")
    return _session


def _reset_session() -> None:
    """Reset the session to force re-initialization on next request."""
    global _session
    _session = None


def _is_kids_shoe(name: str, gender: str) -> bool:
    """Check if a product is a kids shoe."""
    name_lower = name.lower()
    gender_lower = gender.lower() if gender else ""

    kids_indicators = [
        "little kid", "big kid", "toddler", "infant", "kids'", "kids",
        "youth", "grade school", "preschool", "ps)", "gs)", "(td)",
        "child", "boys", "girls"
    ]

    if "kid" in gender_lower or "youth" in gender_lower:
        return True

    return any(indicator in name_lower for indicator in kids_indicators)


def _normalize_brand(brand: str) -> str:
    """Normalize brand name to standard format."""
    brand_map = {
        "nike": "Nike",
        "brooks": "Brooks",
        "hoka": "HOKA",
        "saucony": "Saucony",
        "asics": "ASICS",
        "new balance": "New Balance",
        "adidas": "adidas",
        "on": "On",
        "mizuno": "Mizuno",
        "altra": "Altra",
        "salomon": "Salomon",
        "topo": "Topo Athletic",
        "merrell": "Merrell",
        "karhu": "Karhu",
        "newton": "Newton",
        "diadora": "Diadora",
        "361": "361 Degrees",
        "under armour": "Under Armour",
    }
    return brand_map.get(brand.lower(), brand)


def _normalize_gender(gender: str) -> str:
    """Normalize gender to standard format."""
    gender_lower = gender.lower() if gender else ""

    if "women" in gender_lower or "female" in gender_lower:
        return "Women's"
    if "men" in gender_lower or "male" in gender_lower:
        return "Men's"
    return "Unisex"


def _clean_model_name(description: str, brand: str) -> str:
    """Clean up the product description to get a standardized model name."""
    model = description.strip()

    # Remove brand if already in description
    if brand and model.lower().startswith(brand.lower()):
        model = model[len(brand):].strip()

    # Remove gender indicators
    model = re.sub(r"\b(Men's|Women's|Mens|Womens|Men|Women)\b", "", model, flags=re.IGNORECASE)

    # Clean up extra whitespace
    model = " ".join(model.split())

    # Add brand prefix for consistency
    if brand and not model.lower().startswith(brand.lower()):
        model = f"{brand} {model}"

    return model.strip()


def _parse_price(price_list: list) -> tuple[Optional[float], Optional[float]]:
    """
    Parse price from the price array structure.

    Returns (sale_price, list_price) tuple.
    """
    sale_price = None
    list_price = None

    for price_item in price_list:
        price_type = price_item.get("type", "").upper()
        amount = price_item.get("amount", "")

        try:
            price_val = float(amount.replace(",", ""))
        except (ValueError, TypeError):
            continue

        if price_type in ("SALE", "CLUB", "VIP"):
            if sale_price is None or price_val < sale_price:
                sale_price = price_val
        elif price_type == "MSRP":
            list_price = price_val

    # If no sale price, use list price
    if sale_price is None:
        sale_price = list_price

    return sale_price, list_price


def scrape_category_page(url: str, page: int = 0) -> tuple[list[RoadRunnerProduct], int]:
    """
    Fetch and parse a category page, extracting all products from __NEXT_DATA__.

    Args:
        url: Category URL path (e.g., "/category/Running+Shoes")
        page: Page number (0-indexed)

    Returns:
        Tuple of (products list, total count)
    """
    session = _get_session()
    products = []

    full_url = f"{BASE_URL}{url}"
    if page > 0:
        separator = "&" if "?" in url else "?"
        full_url = f"{full_url}{separator}pageNumber={page}"

    try:
        response = session.get(full_url, timeout=60)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching category page: {e}")
        return [], 0

    soup = BeautifulSoup(response.text, "html.parser")

    # Extract __NEXT_DATA__ JSON
    script = soup.find("script", id="__NEXT_DATA__")
    if not script:
        print("No __NEXT_DATA__ found")
        return [], 0

    try:
        data = json.loads(script.string)
    except json.JSONDecodeError as e:
        print(f"Error parsing __NEXT_DATA__: {e}")
        return [], 0

    # Navigate to search results
    search = data.get("props", {}).get("initialState", {}).get("search", {})
    results = search.get("results", [])
    total_count = search.get("totalSearchCount", 0)

    for item in results:
        try:
            brand = item.get("brand", "")
            category = item.get("category", "")
            description = item.get("description", "")
            gender = item.get("gender", "")
            sku = item.get("sku", "")
            price_list = item.get("price", [])

            # Filter: must be running category
            if category.lower() != "running":
                continue

            # Filter: must be a known running brand
            if brand.lower() not in RUNNING_BRANDS:
                continue

            # Filter: skip kids shoes
            if _is_kids_shoe(description, gender):
                continue

            # Parse prices
            sale_price, list_price = _parse_price(price_list)
            if sale_price is None:
                continue

            # Get image from colorsSkus
            image = ""
            colors_skus = item.get("colorsSkus", [])
            if colors_skus:
                first_color = colors_skus[0]
                images = first_color.get("images", [])
                if images:
                    image = images[0]

            # Build product link
            link = f"{BASE_URL}/product/{sku}"

            # Normalize and clean data
            brand_normalized = _normalize_brand(brand)
            gender_normalized = _normalize_gender(gender)
            model = _clean_model_name(description, brand_normalized)

            products.append(RoadRunnerProduct(
                brand=brand_normalized,
                model=model,
                price=f"${sale_price:.2f}",
                list_price=f"${list_price:.2f}" if list_price else f"${sale_price:.2f}",
                image=image,
                link=link,
                gender=gender_normalized,
            ))

        except Exception as e:
            print(f"Error parsing product: {e}")
            continue

    return products, total_count


def scrape_roadrunnersports_all(max_pages: int = 10) -> list[RoadRunnerProduct]:
    """
    Scrape ALL running shoes from Road Runner Sports.

    Uses category pages with pagination to get comprehensive coverage.

    Args:
        max_pages: Maximum number of pages to fetch per category

    Returns:
        List of RoadRunnerProduct objects, deduplicated by model name
    """
    all_products: dict[str, RoadRunnerProduct] = {}

    print("Scraping Road Runner Sports...")

    for category_url in CATEGORY_URLS:
        print(f"  Category: {category_url}")

        page = 0
        total_for_category = 0

        while page < max_pages:
            products, total_count = scrape_category_page(category_url, page=page)

            if not products:
                if page == 0:
                    print(f"    No products found on first page")
                break

            total_for_category += len(products)
            print(f"    Page {page + 1}: {len(products)} products (total available: {total_count})")

            # Add to dict, keeping lowest price per model
            for product in products:
                key = product.model.lower()
                if key not in all_products:
                    all_products[key] = product
                else:
                    try:
                        existing_price = float(all_products[key].price.replace("$", ""))
                        new_price = float(product.price.replace("$", ""))
                        if new_price < existing_price:
                            all_products[key] = product
                    except ValueError:
                        pass

            # Check if we've fetched all products
            page_size = 48  # Default page size
            if (page + 1) * page_size >= total_count:
                break

            page += 1
            time.sleep(1.0)

        print(f"    Total for category: {total_for_category} products")

    print(f"Scraped {len(all_products)} unique models from Road Runner Sports")
    return list(all_products.values())


def scrape_roadrunnersports() -> list[dict]:
    """
    Main entry point matching existing scraper interface.

    Returns list of shoe dicts compatible with existing add_shoes_to_db().
    """
    print("Scraping Road Runner Sports (API-based)...")
    products = scrape_roadrunnersports_all()
    print(f"Scraped {len(products)} unique shoes from Road Runner Sports")
    return [p.to_dict() for p in products]


if __name__ == "__main__":
    # Test run
    shoes = scrape_roadrunnersports()
    print(f"\nScraped {len(shoes)} shoes total")

    # Group by brand
    by_brand: dict[str, list] = {}
    for shoe in shoes:
        by_brand.setdefault(shoe["brand"], []).append(shoe)

    print(f"\nBrands found: {len(by_brand)}")
    for brand in sorted(by_brand.keys()):
        print(f"  {brand}: {len(by_brand[brand])} models")

    # Print sample
    print("\nSample products:")
    for shoe in shoes[:10]:
        print(f"  {shoe['brand']} - {shoe['model']}: {shoe['price']}")
