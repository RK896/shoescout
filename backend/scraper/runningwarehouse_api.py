"""
Running Warehouse API-based scraper.

Uses direct HTTP requests to the catalog page instead of Selenium.
The catpage endpoint returns ALL products with data in HTML attributes:
- data-gtm_impression_brand: brand name
- data-gtm_impression_name: full product name
- data-gtm_impression_price: price
- data-gtm_impression_code: product code

Much faster and more reliable than browser automation - gets 800+ products
in a single request with no browser needed.
"""
import html
import time
import xml.etree.ElementTree as ET
from typing import Optional
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup


@dataclass
class ShoeProduct:
    """Represents a scraped shoe product."""
    brand: str
    model: str
    price: str
    image: str
    link: str
    retailer: str = "Running Warehouse"

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


# Category URLs - these return ALL products in one request (no pagination needed)
CATALOG_URLS = {
    "men": "https://www.runningwarehouse.com/Mens_Road_Running_Shoes/catpage-MBESTUSE.html",
    "women": "https://www.runningwarehouse.com/Womens_Road_Running_Shoes/catpage-WBESTUSE.html",
}


def _scrape_catalog_page(url: str) -> list[ShoeProduct]:
    """
    Fetch and parse a catalog page, extracting all products.

    The page contains all products with data embedded in HTML attributes.
    No pagination needed - single request gets everything.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=60)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching catalog: {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    products = []

    # Find all product cells with GTM data attributes
    cells = soup.find_all(class_="cattable-wrap-cell")

    # First pass: collect all products
    raw_products = []
    for cell in cells:
        try:
            # Extract data from GTM attributes (most reliable)
            brand = cell.get("data-gtm_impression_brand", "")
            price_str = cell.get("data-gtm_impression_price", "")

            # Get clean model name from the info-name div
            name_tag = cell.find(class_="cattable-wrap-cell-info-name")
            model_name = name_tag.text.strip() if name_tag else ""

            # Get link (strip whitespace including stray \r chars)
            link_tag = cell.find(class_="cattable-wrap-cell-info")
            link = link_tag.get("href", "").strip() if link_tag else ""

            # Get image
            img_tag = cell.find(class_="cattable-wrap-cell-imgwrap-inner-img")
            image = ""
            if img_tag:
                srcset = img_tag.get("srcset", "")
                if srcset:
                    image = html.unescape(srcset.split(",")[0].split()[0])
                else:
                    image = img_tag.get("src", "")

            # Parse price to float for comparison
            try:
                price_val = float(price_str) if price_str else float('inf')
            except ValueError:
                price_val = float('inf')

            # Format price string
            price = f"${price_str}" if price_str and not price_str.startswith("$") else price_str

            if model_name and brand:
                raw_products.append({
                    "brand": brand,
                    "model": model_name,
                    "price": price,
                    "price_val": price_val,
                    "image": image,
                    "link": link,
                })

        except Exception as e:
            print(f"Error parsing product: {e}")
            continue

    # Second pass: deduplicate by model name, keeping lowest price
    best_by_model: dict[str, dict] = {}
    for prod in raw_products:
        model = prod["model"]
        if model not in best_by_model or prod["price_val"] < best_by_model[model]["price_val"]:
            best_by_model[model] = prod

    # Convert to ShoeProduct objects
    for prod in best_by_model.values():
        products.append(ShoeProduct(
            brand=prod["brand"],
            model=prod["model"],
            price=prod["price"],
            image=prod["image"],
            link=prod["link"],
        ))

    return products


def get_shoe_detail(pcode: str) -> Optional[dict]:
    """
    Fetch detailed product info from the cart XML endpoint.

    Useful for getting exact pricing for a specific SKU (with size).

    Args:
        pcode: Full product code with size (e.g., NAP41M3140D)

    Returns:
        Dict with brand, name, price, link, image, category or None on error
    """
    url = f"https://www.runningwarehouse.com/ajax/cartordering.xml?pcode={pcode}&incrementqty=1"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching shoe detail for {pcode}: {e}")
        return None

    try:
        root = ET.fromstring(response.text)
        item = root.find(".//item")

        if item is None:
            return None

        return {
            "code": item.findtext("code", ""),
            "name": item.findtext("name", ""),
            "gtm_name": item.findtext("gtm_name", ""),
            "brand": item.findtext("gtm_brand", ""),
            "category": item.findtext("gtm_category", ""),
            "price": item.findtext("itemprice", ""),
            "link": item.findtext("link", ""),
            "image": item.findtext("image", ""),
        }
    except ET.ParseError as e:
        print(f"Error parsing XML for {pcode}: {e}")
        return None


def scrape_all_shoes(gender: str = "men") -> list[ShoeProduct]:
    """
    Scrape all shoes for a given gender.

    Single request - no pagination needed.

    Args:
        gender: "men" or "women"

    Returns:
        List of ShoeProduct objects
    """
    url = CATALOG_URLS.get(gender, CATALOG_URLS["men"])
    print(f"Scraping {gender}'s running shoes from Running Warehouse...")

    products = _scrape_catalog_page(url)
    print(f"Scraped {len(products)} {gender}'s shoes")

    return products


def scrape_runningwarehouse() -> list[dict]:
    """
    Main entry point matching existing scraper interface.

    Returns list of shoe dicts compatible with existing add_shoes_to_db().
    Scrapes men's shoes only (matching original behavior).
    """
    shoes = scrape_all_shoes(gender="men")
    return [shoe.to_dict() for shoe in shoes]


def scrape_runningwarehouse_all_genders() -> list[dict]:
    """
    Scrape both men's and women's shoes.

    Returns list of shoe dicts.
    """
    all_shoes = []

    for gender in ["men", "women"]:
        shoes = scrape_all_shoes(gender=gender)
        all_shoes.extend([shoe.to_dict() for shoe in shoes])
        time.sleep(2)  # Polite delay between requests

    return all_shoes


if __name__ == "__main__":
    # Test run
    shoes = scrape_runningwarehouse()
    print(f"\nScraped {len(shoes)} shoes total")

    # Print sample
    for shoe in shoes[:5]:
        print(f"  {shoe['brand']} - {shoe['model']}: {shoe['price']}")
