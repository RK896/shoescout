"""
Saucony API-based scraper.

Uses JSON-LD structured data embedded in category pages. Each category page
contains a complete ItemList with all products including name, price, image,
and URL - no pagination needed.

Data source:
    <script type="application/ld+json"> with @type: "ItemList"

Key features:
- No API authentication needed
- All products in single page load per category
- Clean structured data (schema.org format)
- Includes availability status
"""
import json
import re
import time
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup


@dataclass
class SauconyProduct:
    """Represents a scraped Saucony product."""
    brand: str
    model: str
    price: str
    list_price: str
    image: str
    link: str
    gender: str
    available: bool
    retailer: str = "Saucony"

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
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Category URLs - each contains full product listing in JSON-LD
CATEGORY_URLS = {
    "men": "https://www.saucony.com/en/mens-running-shoes",
    "women": "https://www.saucony.com/en/womens-running-shoes",
}


def _clean_model_name(name: str) -> str:
    """
    Clean up the product name to get a standardized model name.

    Saucony names are usually clean like "Endorphin Speed 4"
    """
    model = name.strip()

    # Add brand prefix for consistency with other scrapers
    if not model.lower().startswith("saucony"):
        model = f"Saucony {model}"

    return model


def _extract_json_ld_products(html: str) -> list[dict]:
    """
    Extract products from JSON-LD ItemList in the HTML.

    Returns:
        List of product dicts from the ItemList
    """
    soup = BeautifulSoup(html, "html.parser")
    products = []

    json_ld_scripts = soup.find_all("script", type="application/ld+json")

    for script in json_ld_scripts:
        try:
            data = json.loads(script.string)
            if data.get("@type") == "ItemList":
                items = data.get("itemListElement", [])
                for item in items:
                    product = item.get("item", {})
                    if product.get("@type") == "Product":
                        products.append(product)
        except (json.JSONDecodeError, TypeError):
            continue

    return products


def scrape_saucony_category(url: str, gender: str) -> list[SauconyProduct]:
    """
    Scrape a single Saucony category page.

    Args:
        url: Category page URL
        gender: "Men's" or "Women's"

    Returns:
        List of SauconyProduct objects
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return []

    products = []
    json_ld_products = _extract_json_ld_products(response.text)

    for product in json_ld_products:
        try:
            name = product.get("name", "")
            product_url = product.get("url", "")
            image = product.get("image", "")
            sku = product.get("sku", "")

            offers = product.get("offers", {})
            price = offers.get("price", 0)
            min_price = offers.get("minPrice", price)
            max_price = offers.get("maxPrice", price)
            availability = offers.get("availability", "")

            if not name:
                continue

            # Use min price as the display price
            try:
                price_val = float(min_price) if min_price else 0
            except (ValueError, TypeError):
                continue

            if price_val <= 0:
                continue

            # Format price
            price_str = f"${price_val:.2f}"

            # Check if max_price differs (indicates sale)
            try:
                max_price_val = float(max_price) if max_price else price_val
                list_price_str = f"${max_price_val:.2f}"
            except (ValueError, TypeError):
                list_price_str = price_str

            # Check availability
            is_available = "InStock" in availability if availability else True

            # Clean model name
            model = _clean_model_name(name)

            products.append(SauconyProduct(
                brand="Saucony",
                model=model,
                price=price_str,
                list_price=list_price_str,
                image=image,
                link=product_url,
                gender=gender,
                available=is_available,
            ))

        except Exception as e:
            print(f"Error parsing Saucony product: {e}")
            continue

    return products


def scrape_saucony_all() -> list[SauconyProduct]:
    """
    Scrape ALL running shoes from Saucony across all categories.

    Fetches men's and women's categories and deduplicates by model name.

    Returns:
        List of SauconyProduct objects, deduplicated
    """
    all_products: dict[str, SauconyProduct] = {}  # Dedupe by model

    print("Scraping Saucony...")

    for gender_key, url in CATEGORY_URLS.items():
        gender = "Men's" if gender_key == "men" else "Women's"
        print(f"  Fetching {gender} running shoes...")

        products = scrape_saucony_category(url, gender)
        print(f"    Found {len(products)} products")

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

        time.sleep(1.0)  # Polite delay between requests

    print(f"Scraped {len(all_products)} unique models from Saucony")
    return list(all_products.values())


def scrape_saucony() -> list[dict]:
    """
    Main entry point matching existing scraper interface.

    Returns list of shoe dicts compatible with existing add_shoes_to_db().
    """
    products = scrape_saucony_all()
    return [p.to_dict() for p in products]


if __name__ == "__main__":
    # Test run
    shoes = scrape_saucony()
    print(f"\nScraped {len(shoes)} shoes total")

    # Group by model prefix (first 2 words)
    by_line: dict[str, list] = {}
    for shoe in shoes:
        parts = shoe["model"].split()[:2]
        line = " ".join(parts)
        by_line.setdefault(line, []).append(shoe)

    print(f"\nProduct lines: {len(by_line)}")
    for line in sorted(by_line.keys())[:10]:
        print(f"  {line}: {len(by_line[line])} variants")

    # Print sample
    print("\nSample products:")
    for shoe in shoes[:5]:
        print(f"  {shoe['model']}: {shoe['price']}")
