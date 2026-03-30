"""
Fleet Feet API-based scraper.

Uses server-rendered HTML with product data embedded as JSON in script tags.
Much faster and more reliable than browser automation.

Product data is in <script type="application/json" chuck-replace="product-tile_inner"> tags.
Each contains fields like:
    - product.title: "Men's | HOKA Bondi 9"
    - product.gender: ["Men"] or ["Women"]
    - computed.price: 175
    - computed.originalPrice: 0 (or the original price if on sale)
    - computed.discounted: false/true
    - product.minPrice/maxPrice: price range
    - product.slug: "mens-hoka-bondi-9"
    - sku.photo: image URL
    - product.flags: ["Sale"] or []
"""
import json
import re
import time
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup


@dataclass
class FleetFeetProduct:
    """Represents a scraped Fleet Feet product."""
    brand: str
    model: str
    price: str
    list_price: str
    image: str
    link: str
    gender: str
    on_sale: bool
    retailer: str = "Fleet Feet"

    def to_dict(self) -> dict:
        return {
            "brand": self.brand,
            "model": self.model,
            "price": self.price,
            "image": self.image,
            "link": self.link,
            "retailer": self.retailer,
        }


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
    "Accept": "text/html",
    "Accept-Language": "en-US,en;q=0.9",
}

BASE_URL = "https://www.fleetfeet.com"

# Known running shoe brands
KNOWN_BRANDS = [
    "HOKA", "Hoka", "Brooks", "Nike", "ASICS", "Asics", "New Balance",
    "Saucony", "Adidas", "adidas", "On", "Altra", "Mizuno", "Salomon",
    "Reebok", "Puma", "Under Armour", "Topo", "Karhu", "Diadora",
    "361°", "361 Degrees", "La Sportiva",
]

# Product slugs to filter out (non-running shoes)
EXCLUDED_SLUGS = [
    "insole", "sock", "sandal", "bra", "shirt", "shorts", "tight",
    "jacket", "pant", "cap", "hat", "visor", "glove", "sleeve",
    "belt", "pack", "bottle", "sunglasses", "watch", "accessory",
]


def fetch_fleetfeet_page(gender: str, page: int) -> Optional[str]:
    """
    Fetch a Fleet Feet browse page for the given gender and page number.

    Args:
        gender: "mens" or "womens"
        page: Page number (1-indexed)

    Returns:
        HTML content as string, or None on error
    """
    url = f"{BASE_URL}/browse/shoes/{gender}?page={page}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Error fetching Fleet Feet page {page} for {gender}: {e}")
        return None


def extract_products(html: str) -> list[dict]:
    """
    Extract product data from Fleet Feet HTML.

    Finds all <script type="application/json" chuck-replace="product-tile_inner">
    tags and parses each as JSON.

    Args:
        html: HTML content from Fleet Feet browse page

    Returns:
        List of raw product dicts extracted from JSON
    """
    soup = BeautifulSoup(html, "html.parser")
    products = []

    # Find all product JSON script tags
    script_tags = soup.find_all("script", {"type": "application/json", "chuck-replace": "product-tile_inner"})

    for script in script_tags:
        try:
            data = json.loads(script.string)
            products.append(data)
        except (json.JSONDecodeError, TypeError) as e:
            # Skip malformed JSON
            continue

    return products


def _extract_brand(title: str) -> str:
    """
    Extract brand from product title.

    Fleet Feet titles are like "Men's | HOKA Bondi 9" or "Women's | Brooks Ghost 16"
    The brand is typically the first word after the gender prefix.

    Args:
        title: Product title

    Returns:
        Brand name
    """
    # Remove gender prefix
    clean_title = re.sub(r"^(Men's|Women's|Unisex)\s*\|\s*", "", title)

    # Check for known brands at the start
    for brand in KNOWN_BRANDS:
        if clean_title.lower().startswith(brand.lower()):
            # Return the brand with proper casing
            return brand.upper() if brand.lower() in ("hoka", "asics") else brand

    # Fallback: first word is usually the brand
    words = clean_title.split()
    if words:
        # Handle "New Balance" as a two-word brand
        if len(words) >= 2 and words[0].lower() == "new" and words[1].lower() == "balance":
            return "New Balance"
        return words[0]

    return "Unknown"


def _extract_model_name(title: str, brand: str) -> str:
    """
    Extract model name from product title.

    Removes gender prefix and brand to get the model name.

    Args:
        title: Product title (e.g., "Men's | HOKA Bondi 9")
        brand: Extracted brand name

    Returns:
        Model name (e.g., "Bondi 9")
    """
    # Remove gender prefix
    clean_title = re.sub(r"^(Men's|Women's|Unisex)\s*\|\s*", "", title)

    # Remove brand prefix (case-insensitive)
    if brand.lower() == "new balance":
        # Handle two-word brand
        clean_title = re.sub(r"^New\s+Balance\s+", "", clean_title, flags=re.IGNORECASE)
    else:
        clean_title = re.sub(rf"^{re.escape(brand)}\s+", "", clean_title, flags=re.IGNORECASE)

    return clean_title.strip()


def _parse_gender(gender_list: list) -> str:
    """
    Parse gender from Fleet Feet gender array.

    Args:
        gender_list: List like ["Men"], ["Women"], or ["Men", "Women"]

    Returns:
        "Men's", "Women's", or "Unisex"
    """
    if not gender_list:
        return "Unisex"

    if len(gender_list) >= 2:
        return "Unisex"

    gender = gender_list[0].lower()
    if gender == "men":
        return "Men's"
    elif gender == "women":
        return "Women's"

    return "Unisex"


def _transform_image_url(photo_url: str) -> str:
    """
    Transform Fleet Feet image URL to use their CDN.

    Args:
        photo_url: Original sku.photo URL

    Returns:
        Transformed CDN URL
    """
    if not photo_url:
        return ""

    # If it's already a full URL, extract the filename and rebuild
    if "ffecom.s3.amazonaws.com" in photo_url:
        # Extract the filename part
        parts = photo_url.split("/")
        if parts:
            filename = parts[-1]
            return f"https://cdn.fleetfeet.com/productTile/products/{filename}"

    # If it's already a CDN URL, return as-is
    if "cdn.fleetfeet.com" in photo_url:
        return photo_url

    return photo_url


def _is_excluded_product(slug: str) -> bool:
    """
    Check if a product should be excluded based on its slug.

    Args:
        slug: Product slug (e.g., "mens-hoka-bondi-9")

    Returns:
        True if product should be excluded
    """
    slug_lower = slug.lower()
    return any(excluded in slug_lower for excluded in EXCLUDED_SLUGS)


def parse_product(data: dict) -> Optional[FleetFeetProduct]:
    """
    Parse a raw product dict into a FleetFeetProduct.

    Args:
        data: Raw product dict from JSON

    Returns:
        FleetFeetProduct or None if product should be skipped
    """
    try:
        slug = data.get("product.slug", "")

        # Filter out non-shoe products
        if _is_excluded_product(slug):
            return None

        title = data.get("product.title", "")
        if not title:
            return None

        # Extract brand and model
        brand = _extract_brand(title)
        model = _extract_model_name(title, brand)

        # Full model name with brand
        full_model = f"{brand} {model}"

        # Parse gender
        gender_list = data.get("product.gender", [])
        gender = _parse_gender(gender_list)

        # Parse prices
        price = data.get("computed.price", 0)
        original_price = data.get("computed.originalPrice", 0)
        is_discounted = data.get("computed.discounted", False)

        # Format prices
        if price:
            price_str = f"${price:.2f}" if isinstance(price, float) else f"${price}"
        else:
            return None  # Skip products without price

        if is_discounted and original_price and original_price > 0:
            list_price_str = f"${original_price:.2f}" if isinstance(original_price, float) else f"${original_price}"
        else:
            list_price_str = price_str

        # Build URL
        link = f"{BASE_URL}/products/{slug}" if slug else ""

        # Transform image URL
        photo_url = data.get("sku.photo", "")
        image_url = _transform_image_url(photo_url)

        return FleetFeetProduct(
            brand=brand,
            model=full_model,
            price=price_str,
            list_price=list_price_str,
            image=image_url,
            link=link,
            gender=gender,
            on_sale=is_discounted,
        )

    except Exception as e:
        print(f"Error parsing Fleet Feet product: {e}")
        return None


def _has_next_page(html: str) -> bool:
    """
    Check if there's a next page link in the HTML.

    Args:
        html: HTML content

    Returns:
        True if there's a next page
    """
    soup = BeautifulSoup(html, "html.parser")

    # Look for "Next" link or pagination with active next button
    next_link = soup.find("a", string=re.compile(r"next", re.IGNORECASE))
    if next_link:
        return True

    # Look for pagination controls
    pagination = soup.find(class_=re.compile(r"pagination", re.IGNORECASE))
    if pagination:
        # Check for a next arrow or number link
        next_arrow = pagination.find("a", class_=re.compile(r"next", re.IGNORECASE))
        if next_arrow:
            return True

    return False


def scrape_fleetfeet_gender(gender: str, max_pages: int = 20) -> list[FleetFeetProduct]:
    """
    Scrape all shoes for a given gender.

    Paginates through all browse pages until no more products are found.

    Args:
        gender: "mens" or "womens"
        max_pages: Maximum pages to fetch (safety limit)

    Returns:
        List of FleetFeetProduct objects
    """
    all_products: dict[str, FleetFeetProduct] = {}  # Dedupe by model+gender
    page = 1

    print(f"Scraping Fleet Feet {gender} shoes...")

    while page <= max_pages:
        html = fetch_fleetfeet_page(gender, page)
        if not html:
            break

        raw_products = extract_products(html)

        if not raw_products:
            print(f"  Page {page}: no products found, stopping")
            break

        page_count = 0
        for raw in raw_products:
            product = parse_product(raw)
            if product:
                # Dedupe key: model name (lowercase) + gender
                key = f"{product.model.lower()}|{product.gender}"
                if key not in all_products:
                    all_products[key] = product
                    page_count += 1
                else:
                    # Keep the one with lower price
                    existing = all_products[key]
                    try:
                        existing_price = float(existing.price.replace("$", "").replace(",", ""))
                        new_price = float(product.price.replace("$", "").replace(",", ""))
                        if new_price < existing_price:
                            all_products[key] = product
                    except ValueError:
                        pass

        print(f"  Page {page}: {len(raw_products)} raw products, {page_count} new unique shoes")

        # Check if we should continue
        if not _has_next_page(html):
            print(f"  No next page found, stopping")
            break

        page += 1
        time.sleep(1.5)  # Polite delay between requests

    products = list(all_products.values())
    print(f"Scraped {len(products)} unique {gender} shoes from Fleet Feet")
    return products


def scrape_fleetfeet_all_genders() -> list[dict]:
    """
    Scrape both men's and women's shoes.

    Returns:
        List of shoe dicts
    """
    all_shoes = []

    for gender in ["mens", "womens"]:
        products = scrape_fleetfeet_gender(gender)
        all_shoes.extend([p.to_dict() for p in products])
        time.sleep(2)  # Polite delay between genders

    return all_shoes


def scrape_fleetfeet() -> list[dict]:
    """
    Main entry point matching existing scraper interface.

    Returns list of shoe dicts compatible with existing add_shoes_to_db().
    Scrapes both men's and women's shoes.
    """
    print("Scraping Fleet Feet...")
    shoes = scrape_fleetfeet_all_genders()
    print(f"Scraped {len(shoes)} total shoes from Fleet Feet")
    return shoes


if __name__ == "__main__":
    # Test run
    shoes = scrape_fleetfeet()
    print(f"\nScraped {len(shoes)} shoes total")

    # Print sample
    for shoe in shoes[:10]:
        print(f"  {shoe['brand']} - {shoe['model']}: {shoe['price']}")
