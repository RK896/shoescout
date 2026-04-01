"""
Holabird Sports API-based scraper.

Uses the third-party SearchServerAPI that Holabird uses for product search.
Returns clean JSON with product data, prices, variants, and availability.

API endpoint:
    GET https://searchserverapi.com/getresults?api_key=1T0U8M9s3R&q={query}&facets=true&itemsPerPage=100&startIndex={offset}

Key features:
- Pagination support via startIndex
- Variant information (size, width, availability)
- Tags contain faceted data (gender, brand, category)
"""
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional

import requests


@dataclass
class ShoeVariant:
    """Represents a shoe size/width variant."""
    size: str
    width: str
    price: float
    list_price: float
    available: bool
    variant_id: str
    link: str

    def to_dict(self) -> dict:
        return {
            "size": self.size,
            "width": self.width,
            "price": self.price,
            "list_price": self.list_price,
            "available": self.available,
            "variant_id": self.variant_id,
            "link": self.link,
        }


@dataclass
class HolabirdProduct:
    """Represents a scraped Holabird Sports product."""
    brand: str
    model: str
    price: str
    list_price: str
    image: str
    link: str
    gender: str
    variants: list[ShoeVariant] = field(default_factory=list)
    retailer: str = "Holabird Sports"

    def to_dict(self) -> dict:
        size_variants = [variant.to_dict() for variant in self.variants]
        available_sizes = sorted(
            {variant.size for variant in self.variants if variant.available and variant.size}
        )
        available_widths = sorted(
            {variant.width for variant in self.variants if variant.available and variant.width}
        )
        return {
            "brand": self.brand,
            "model": self.model,
            "price": self.price,
            "image": self.image,
            "link": self.link,
            "gender": self.gender,
            "retailer": self.retailer,
            "size_variants": size_variants,
            "available_sizes": available_sizes,
            "available_widths": available_widths,
        }


# API configuration
API_KEY = "1T0U8M9s3R"
BASE_URL = "https://searchserverapi.com/getresults"
HOLABIRD_BASE = "https://www.holabirdsports.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.holabirdsports.com",
    "Referer": "https://www.holabirdsports.com/",
}

# Brand-specific running shoe searches for comprehensive coverage
BRAND_SEARCHES = [
    "nike running shoes",
    "brooks running shoes",
    "hoka running shoes",
    "saucony running shoes",
    "new balance running shoes",
    "asics running shoes",
    "adidas running shoes",
    "on running shoes",
    "mizuno running shoes",
]


def _extract_gender(tags: str, title: str) -> Optional[str]:
    """
    Extract gender from tags string.

    Tags format: "...Gender_Womens[:ATTR:]Brand_Nike..."

    Returns:
        "Men's", "Women's", or None if kids/youth
    """
    tags_lower = tags.lower() if tags else ""
    title_lower = title.lower() if title else ""

    # Skip kids/youth products
    if "kids" in tags_lower or "youth" in tags_lower:
        return None
    if "kids" in title_lower or "youth" in title_lower:
        return None
    if "little kid" in title_lower or "big kid" in title_lower:
        return None

    # Extract gender from tags
    if "gender_womens" in tags_lower or "gender_women" in tags_lower:
        return "Women's"
    if "gender_mens" in tags_lower or "gender_men" in tags_lower:
        return "Men's"

    # Try to infer from title
    if "women" in title_lower or "womens" in title_lower:
        return "Women's"
    if "men" in title_lower and "women" not in title_lower:
        return "Men's"

    return "Unisex"


def _is_running_shoe(tags: str, title: str) -> bool:
    """
    Check if the product is a running shoe.

    Returns:
        True if this is a running shoe
    """
    tags_lower = tags.lower() if tags else ""
    title_lower = title.lower() if title else ""

    # Check tags for running category
    if "running" in tags_lower:
        return True

    # Check title
    if "running" in title_lower:
        return True

    return False


def _clean_model_name(title: str, brand: str) -> str:
    """
    Clean up the product title to get a standardized model name.

    Holabird titles often include color: "Nike Pegasus 41 Men's Black/White"
    """
    model = title.strip()

    # Remove brand prefix if present
    if brand and model.lower().startswith(brand.lower()):
        model = model[len(brand):].strip()

    # Remove color suffix (usually after the last word that looks like a model name)
    # Colors often contain / like "Black/White" or color names
    # This is tricky - for now, keep the full name for accuracy

    # Remove gender from model name
    model = re.sub(r"\b(Men's|Women's|Mens|Womens|Men|Women)\b", "", model, flags=re.IGNORECASE)

    # Clean up extra whitespace
    model = " ".join(model.split())

    # Add brand prefix back for consistency
    if brand and not model.lower().startswith(brand.lower()):
        model = f"{brand} {model}"

    return model.strip()


def _parse_variants(shopify_variants: list) -> list[ShoeVariant]:
    """Parse variant information from shopify_variants array."""
    variants = []

    for v in shopify_variants or []:
        try:
            options = v.get("options", {})
            size = options.get("Size", "")
            width = options.get("Width", "")

            price = float(v.get("price", 0))
            list_price = float(v.get("list_price", 0)) or price
            available = v.get("available") == "1"
            variant_id = str(v.get("variant_id", ""))
            link = v.get("link", "")

            if size:  # Only add if we have a size
                variants.append(ShoeVariant(
                    size=size,
                    width=width,
                    price=price,
                    list_price=list_price,
                    available=available,
                    variant_id=variant_id,
                    link=link,
                ))
        except (ValueError, TypeError):
            continue

    return variants


def _variant_identity(variant: ShoeVariant) -> tuple[str, str, str]:
    """Create a stable key for merging duplicate variant records."""
    variant_id = variant.variant_id or ""
    if variant_id:
        return (variant_id, "", "")
    return (variant.size.strip().lower(), variant.width.strip().lower(), variant.link.strip())


def _merge_variants(existing: list[ShoeVariant], incoming: list[ShoeVariant]) -> list[ShoeVariant]:
    """Merge variant lists while preserving the lowest price and any available stock flags."""
    merged: dict[tuple[str, str, str], ShoeVariant] = {}

    for variant in existing + incoming:
        key = _variant_identity(variant)
        current = merged.get(key)
        if current is None:
            merged[key] = variant
            continue

        current.available = current.available or variant.available
        if variant.price and (not current.price or variant.price < current.price):
            current.price = variant.price
        if variant.list_price and (not current.list_price or variant.list_price < current.list_price):
            current.list_price = variant.list_price
        if not current.link and variant.link:
            current.link = variant.link
        if not current.width and variant.width:
            current.width = variant.width
        if not current.size and variant.size:
            current.size = variant.size

    return list(merged.values())


def search_holabird(query: str, start: int = 0, items_per_page: int = 100) -> dict:
    """
    Search Holabird Sports API for products.

    Args:
        query: Search query (e.g., "nike running shoes")
        start: Starting index for pagination (0-indexed)
        items_per_page: Number of results per page (max 100)

    Returns:
        Raw API response as dict, or empty dict on error
    """
    params = {
        "api_key": API_KEY,
        "q": query,
        "facets": "true",
        "itemsPerPage": items_per_page,
        "startIndex": start,
    }

    url = f"{BASE_URL}?{urllib.parse.urlencode(params)}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error searching Holabird for '{query}': {e}")
        return {}
    except ValueError as e:
        print(f"Error parsing Holabird response for '{query}': {e}")
        return {}


def parse_holabird_response(response: dict) -> list[HolabirdProduct]:
    """
    Parse the Holabird API response and extract products.

    Filters to only running shoes and excludes kids/youth.

    Returns:
        List of HolabirdProduct objects
    """
    products = []

    items = response.get("items", [])

    for item in items:
        try:
            title = item.get("title", "")
            brand = item.get("vendor", "")
            tags = item.get("tags", "")
            link = item.get("link", "")
            image = item.get("image_link", "")
            price_str = item.get("price", "")
            list_price_str = item.get("list_price", "")
            shopify_variants = item.get("shopify_variants", [])

            # Skip if missing essential data
            if not title or not brand:
                continue

            # Filter: must be a running shoe
            if not _is_running_shoe(tags, title):
                continue

            # Extract gender (returns None for kids/youth)
            gender = _extract_gender(tags, title)
            if gender is None:
                continue

            # Parse prices
            try:
                price = float(price_str) if price_str else 0
                list_price = float(list_price_str) if list_price_str else price
            except ValueError:
                continue

            if price <= 0:
                continue

            # Format prices
            price_formatted = f"${price:.2f}"
            list_price_formatted = f"${list_price:.2f}"

            # Build full URL
            full_link = f"{HOLABIRD_BASE}{link}" if link and not link.startswith("http") else link

            # Clean up model name
            model = _clean_model_name(title, brand)

            # Parse variants
            variants = _parse_variants(shopify_variants)

            products.append(HolabirdProduct(
                brand=brand,
                model=model,
                price=price_formatted,
                list_price=list_price_formatted,
                image=image,
                link=full_link,
                gender=gender,
                variants=variants,
            ))

        except Exception as e:
            print(f"Error parsing Holabird product: {e}")
            continue

    return products


def scrape_holabird_all() -> list[HolabirdProduct]:
    """
    Scrape ALL running shoes from Holabird using brand-specific searches with pagination.

    Iterates through major running shoe brands and paginates through all results.

    Returns:
        List of HolabirdProduct objects, deduplicated by model name
    """
    all_products: dict[str, HolabirdProduct] = {}  # Dedupe by model

    print("Scraping Holabird Sports...")

    for search_idx, search_query in enumerate(BRAND_SEARCHES):
        print(f"  Searching: {search_query} ({search_idx + 1}/{len(BRAND_SEARCHES)})")

        start = 0
        items_per_page = 100
        total_for_query = 0

        while True:
            response = search_holabird(search_query, start=start, items_per_page=items_per_page)

            if not response:
                break

            total_items = response.get("totalItems", 0)
            items = response.get("items", [])

            if not items:
                break

            products = parse_holabird_response(response)
            total_for_query += len(products)

            # Add to dict, keeping lowest price per model
            for product in products:
                key = product.model.lower()
                if key not in all_products:
                    all_products[key] = product
                else:
                    existing = all_products[key]
                    existing.variants = _merge_variants(existing.variants, product.variants)
                    # Keep the one with lower price
                    try:
                        existing_price = float(existing.price.replace("$", ""))
                        new_price = float(product.price.replace("$", ""))
                        if new_price < existing_price:
                            all_products[key] = product
                            all_products[key].variants = _merge_variants(
                                existing.variants,
                                product.variants,
                            )
                    except ValueError:
                        pass

            # Check if we've fetched all items for this query
            if start + items_per_page >= total_items:
                break

            start += items_per_page
            time.sleep(0.5)  # Small delay between pages

        print(f"    Found {total_for_query} running shoes (total available: {total_items if 'total_items' in dir() else 'N/A'})")
        time.sleep(1.0)  # Delay between brand searches

    print(f"Scraped {len(all_products)} unique models from Holabird")
    return list(all_products.values())


def scrape_holabird() -> list[dict]:
    """
    Main entry point matching existing scraper interface.

    Uses the full catalog browsing approach to get ALL running shoes.

    Returns list of shoe dicts compatible with existing add_shoes_to_db().
    """
    print("Scraping Holabird Sports...")
    products = scrape_holabird_all()
    print(f"Scraped {len(products)} unique shoes from Holabird")
    return [p.to_dict() for p in products]


if __name__ == "__main__":
    # Test run
    shoes = scrape_holabird()
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
    for shoe in shoes[:5]:
        print(f"  {shoe['brand']} - {shoe['model']}: {shoe['price']}")
