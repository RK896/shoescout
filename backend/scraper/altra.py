"""
Altra Running API-based scraper.

Altra uses Salesforce Commerce Cloud (SFCC/Demandware) similar to Brooks.
Uses the Search-UpdateGrid endpoint to fetch product listings.

API endpoint:
    GET https://www.altrarunning.com/on/demandware.store/Sites-alt-us-Site/en_US/Search-UpdateGrid
    Parameters:
        - cgid: Category ID
        - start: Offset for pagination
        - sz: Page size

Key features:
- Session-based requests with proper cookies
- Parses HTML response for product tiles
- Extracts data from data attributes and price elements
- Deduplicates by model name, keeping lowest price
"""
import json
import re
import time
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup


@dataclass
class AltraProduct:
    """Represents a scraped Altra Running product."""
    brand: str
    model: str
    price: str
    list_price: str
    image: str
    link: str
    gender: str
    on_sale: bool
    retailer: str = "Altra"

    def to_dict(self) -> dict:
        return {
            "brand": self.brand,
            "model": self.model,
            "price": self.price,
            "image": self.image,
            "link": self.link,
            "retailer": self.retailer,
        }


BASE_URL = "https://www.altrarunning.com"
API_URL = f"{BASE_URL}/on/demandware.store/Sites-alt-us-Site/en_US/Search-UpdateGrid"

# Category IDs for different shoe types
CATEGORIES = {
    "mens_road": "men-shoes-road",
    "womens_road": "women-shoes-road",
    "mens_trail": "men-shoes-trail",
    "womens_trail": "women-shoes-trail",
    "mens_all": "men-shoes",
    "womens_all": "women-shoes",
}

# Alternative category page URLs (direct HTML pages)
CATEGORY_PAGES = {
    "mens_road": f"{BASE_URL}/en-us/men/shoes/road",
    "womens_road": f"{BASE_URL}/en-us/women/shoes/road",
    "mens_trail": f"{BASE_URL}/en-us/men/shoes/trail",
    "womens_trail": f"{BASE_URL}/en-us/women/shoes/trail",
    "mens_all": f"{BASE_URL}/en-us/men/shoes",
    "womens_all": f"{BASE_URL}/en-us/women/shoes",
}

# Global session
_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    """Get or create a requests session with proper headers and cookies."""
    global _session

    if _session is not None:
        return _session

    print("Initializing Altra session...")
    _session = requests.Session()
    _session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    })

    # Visit main page to get session cookies
    try:
        _session.get(f"{BASE_URL}/en-us/", timeout=30)
    except requests.RequestException as e:
        print(f"Warning: Failed to initialize Altra session: {e}")

    # Update headers for subsequent requests
    _session.headers.update({
        "Accept": "text/html, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{BASE_URL}/en-us/men/shoes",
    })

    return _session


def _reset_session() -> None:
    """Reset the session to force re-initialization."""
    global _session
    _session = None


def fetch_altra_api(category: str, start: int = 0, page_size: int = 48) -> Optional[str]:
    """
    Fetch products using the SFCC Search-UpdateGrid API.

    Args:
        category: Category ID (e.g., "men-shoes-road")
        start: Pagination offset
        page_size: Number of products per page

    Returns:
        HTML content or None on error
    """
    session = _get_session()

    params = {
        "cgid": category,
        "start": start,
        "sz": page_size,
    }

    try:
        response = session.get(API_URL, params=params, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Error fetching Altra API (category={category}, start={start}): {e}")
        return None


def fetch_altra_page(url: str) -> Optional[str]:
    """
    Fetch a category page directly.

    Args:
        url: Full category page URL

    Returns:
        HTML content or None on error
    """
    session = _get_session()

    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return None


def extract_products_from_html(html: str) -> list[dict]:
    """
    Extract product data from Altra HTML response.

    Looks for product tiles with data-pid attributes and extracts
    name, price, image, and link information.
    """
    soup = BeautifulSoup(html, "html.parser")
    products = []

    # First try JSON-LD structured data
    json_ld_scripts = soup.find_all("script", type="application/ld+json")
    for script in json_ld_scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                if data.get("@type") == "ItemList":
                    for item in data.get("itemListElement", []):
                        product = item.get("item", {})
                        if product.get("@type") == "Product":
                            products.append({
                                "name": product.get("name", ""),
                                "url": product.get("url", ""),
                                "image": product.get("image", ""),
                                "price": product.get("offers", {}).get("price"),
                                "list_price": product.get("offers", {}).get("highPrice"),
                            })
                elif data.get("@type") == "Product":
                    products.append({
                        "name": data.get("name", ""),
                        "url": data.get("url", ""),
                        "image": data.get("image", ""),
                        "price": data.get("offers", {}).get("price"),
                        "list_price": data.get("offers", {}).get("highPrice"),
                    })
        except (json.JSONDecodeError, TypeError):
            continue

    if products:
        return products

    # Fallback: Parse product tiles from HTML
    # SFCC typically uses data-pid for product containers
    tiles = soup.select('[data-pid], .b-product_tile, .product-tile, [class*="product-tile"]')

    for tile in tiles:
        try:
            pid = tile.get("data-pid", "")

            # Extract name
            name = ""
            name_el = tile.select_one('[class*="product-name"], [class*="tile-name"], .b-tile-name, h2, h3')
            if name_el:
                name = name_el.get_text(strip=True)
            if not name:
                name = tile.get("data-product-name", "") or tile.get("data-name", "")

            if not name:
                continue

            # Extract price - look for current/sale price first
            price = ""
            price_el = tile.select_one('.b-price-item, [class*="sales"], [class*="sale-price"], .price-sales')
            if price_el:
                price_text = price_el.get_text(strip=True)
                match = re.search(r'\$[\d,]+\.?\d*', price_text)
                if match:
                    price = match.group(0)

            if not price:
                price_el = tile.select_one('[class*="price"]')
                if price_el:
                    price_text = price_el.get_text(strip=True)
                    match = re.search(r'\$[\d,]+\.?\d*', price_text)
                    if match:
                        price = match.group(0)

            # Extract original/list price
            list_price = ""
            list_price_el = tile.select_one('[class*="list-price"], [class*="strike"], .b-price-item--old, del, s')
            if list_price_el:
                list_text = list_price_el.get_text(strip=True)
                match = re.search(r'\$[\d,]+\.?\d*', list_text)
                if match:
                    list_price = match.group(0)

            # Extract link
            link = ""
            link_el = tile.select_one('a[href*="/product/"], a[href*="/shoes/"], a[href]')
            if link_el:
                href = link_el.get("href", "")
                if href.startswith("http"):
                    link = href
                elif href.startswith("/"):
                    link = BASE_URL + href
                elif href:
                    link = BASE_URL + "/" + href

            # Extract image
            image = ""
            img_el = tile.select_one('img[src], img[data-src], picture source[srcset]')
            if img_el:
                if img_el.name == "source":
                    srcset = img_el.get("srcset", "")
                    if srcset:
                        image = srcset.split(",")[0].split()[0]
                else:
                    image = img_el.get("src") or img_el.get("data-src") or ""

            products.append({
                "pid": pid,
                "name": name,
                "price": price,
                "list_price": list_price,
                "url": link,
                "image": image,
            })

        except Exception as e:
            print(f"Error parsing Altra product tile: {e}")
            continue

    return products


def parse_product(data: dict, gender: str) -> Optional[AltraProduct]:
    """
    Parse a raw product dict into an AltraProduct.

    Args:
        data: Raw product dict
        gender: "Men's" or "Women's"

    Returns:
        AltraProduct or None if invalid
    """
    name = data.get("name", "")
    if not name:
        return None

    price = data.get("price", "")
    list_price = data.get("list_price", "") or price

    # Format price if numeric
    if isinstance(price, (int, float)):
        price = f"${float(price):.2f}"
    if isinstance(list_price, (int, float)):
        list_price = f"${float(list_price):.2f}"

    if not price:
        return None

    on_sale = bool(list_price and list_price != price)

    # Format model name
    model = name.strip()
    if not model.lower().startswith("altra"):
        model = f"Altra {model}"

    return AltraProduct(
        brand="Altra",
        model=model,
        price=price,
        list_price=list_price,
        image=data.get("image", ""),
        link=data.get("url", ""),
        gender=gender,
        on_sale=on_sale,
    )


def scrape_altra_category(category_key: str, max_pages: int = 5) -> list[AltraProduct]:
    """
    Scrape all products from an Altra category.

    Tries the API endpoint first, falls back to direct page scraping.

    Args:
        category_key: Key for CATEGORIES dict
        max_pages: Maximum pages to fetch

    Returns:
        List of AltraProduct objects
    """
    gender = "Men's" if "mens" in category_key else "Women's"
    all_products: dict[str, AltraProduct] = {}

    print(f"Scraping Altra {category_key}...")

    # Try API endpoint first
    category_id = CATEGORIES.get(category_key, "")
    if category_id:
        start = 0
        page_size = 48
        page = 1

        while page <= max_pages:
            html = fetch_altra_api(category_id, start=start, page_size=page_size)
            if not html or len(html) < 100:
                break

            raw_products = extract_products_from_html(html)
            if not raw_products:
                break

            new_count = 0
            for raw in raw_products:
                product = parse_product(raw, gender)
                if product:
                    key = product.model.lower()
                    if key not in all_products:
                        all_products[key] = product
                        new_count += 1
                    else:
                        # Keep lower price
                        try:
                            existing_price = float(all_products[key].price.replace("$", "").replace(",", ""))
                            new_price = float(product.price.replace("$", "").replace(",", ""))
                            if new_price < existing_price:
                                all_products[key] = product
                        except ValueError:
                            pass

            print(f"  Page {page}: {len(raw_products)} products, {new_count} new unique")

            if len(raw_products) < page_size:
                break

            start += page_size
            page += 1
            time.sleep(1.0)

    # Fallback to direct page scraping if API didn't work
    if not all_products:
        url = CATEGORY_PAGES.get(category_key, "")
        if url:
            print(f"  Trying direct page: {url}")
            html = fetch_altra_page(url)
            if html:
                raw_products = extract_products_from_html(html)
                for raw in raw_products:
                    product = parse_product(raw, gender)
                    if product:
                        key = product.model.lower()
                        if key not in all_products:
                            all_products[key] = product

    products = list(all_products.values())
    print(f"  Scraped {len(products)} unique {category_key} shoes")
    return products


def scrape_altra_all() -> list[dict]:
    """
    Scrape both men's and women's shoes.

    Returns:
        List of shoe dicts
    """
    all_products: dict[str, AltraProduct] = {}

    categories = [
        "mens_road",
        "womens_road",
        "mens_trail",
        "womens_trail",
    ]

    for category in categories:
        products = scrape_altra_category(category)

        for product in products:
            key = product.model.lower()
            if key not in all_products:
                all_products[key] = product
            else:
                # Keep lower price
                try:
                    existing_price = float(all_products[key].price.replace("$", "").replace(",", ""))
                    new_price = float(product.price.replace("$", "").replace(",", ""))
                    if new_price < existing_price:
                        all_products[key] = product
                except ValueError:
                    pass

        time.sleep(1.5)

    return [p.to_dict() for p in all_products.values()]


def scrape_altra() -> list[dict]:
    """
    Main entry point matching existing scraper interface.

    Returns list of shoe dicts compatible with add_shoes_to_db().
    """
    print("Scraping Altra Running...")
    shoes = scrape_altra_all()
    print(f"Scraped {len(shoes)} total shoes from Altra")
    return shoes


if __name__ == "__main__":
    # Test run
    shoes = scrape_altra()
    print(f"\nScraped {len(shoes)} shoes total")

    for shoe in shoes[:10]:
        print(f"  {shoe['model']}: {shoe['price']}")
