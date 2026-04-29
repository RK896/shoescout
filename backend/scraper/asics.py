"""
ASICS API-based scraper.

Uses the Salesforce Commerce Cloud (SFCC) Search-UpdateGrid endpoint.
ASICS uses Demandware/SFCC for their e-commerce platform.

API endpoint:
    GET https://www.asics.com/on/demandware.store/Sites-asics-us-Site/en_US/Search-UpdateGrid
    Parameters:
        - cgid: Category ID (e.g., "aa10201000" for men's running)
        - start: Offset for pagination (0, 24, 48, ...)
        - sz: Page size

Fallback: Also tries the product listing page with HTML parsing.
"""
import json
import re
import time
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup


@dataclass
class AsicsProduct:
    """Represents a scraped ASICS product."""
    brand: str
    model: str
    price: str
    list_price: str
    image: str
    link: str
    gender: str
    on_sale: bool
    retailer: str = "ASICS"

    def to_dict(self) -> dict:
        return {
            "brand": self.brand,
            "model": self.model,
            "price": self.price,
            "image": self.image,
            "link": self.link,
            "retailer": self.retailer,
        }


BASE_URL = "https://www.asics.com"
API_URL = f"{BASE_URL}/on/demandware.store/Sites-asics-us-Site/en_US/Search-UpdateGrid"

# Category URLs for running shoes (from existing scraper)
CATEGORY_URLS = {
    "mens": f"{BASE_URL}/us/en-us/mens-running-shoes/c/aa10201000/",
    "womens": f"{BASE_URL}/us/en-us/womens-running-shoes/c/aa20201000/",
}

# Category IDs for API
CATEGORY_IDS = {
    "mens": "aa10201000",
    "womens": "aa20201000",
}

# Global session - initialized lazily
_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    """
    Get or create a requests session with valid ASICS cookies.
    """
    global _session

    if _session is not None:
        return _session

    print("Initializing ASICS session...")
    _session = requests.Session()
    _session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Sec-Ch-Ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    })

    # Visit main page and category page to build a valid session
    try:
        resp = _session.get(f"{BASE_URL}/us/en-us/", timeout=30)
        print(f"  Session init: status {resp.status_code}")
        if resp.status_code == 200:
            time.sleep(2)
            _session.get(f"{BASE_URL}/us/en-us/mens-running-shoes/c/aa10201000/", timeout=30)
    except requests.RequestException as e:
        print(f"Warning: Failed to initialize ASICS session: {e}")

    return _session


def _reset_session() -> None:
    """Reset the session to force re-initialization on next request."""
    global _session
    _session = None


def _extract_json_ld_products(html: str) -> list[dict]:
    """Extract products from JSON-LD ItemList in the HTML."""
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
            elif data.get("@type") == "Product":
                products.append(data)

        except (json.JSONDecodeError, TypeError):
            continue

    return products


def _extract_products_from_html(html: str) -> list[dict]:
    """
    Extract products from ASICS HTML page using CSS selectors.

    ASICS product tiles use classes like:
    - .product-tile: Main container
    - .product-name or .product-tile__text: Product name
    - .price-sales: Sale price
    - .product-tile__link: Product link
    """
    soup = BeautifulSoup(html, "html.parser")
    products = []

    # Find product tiles
    tiles = soup.select(".product-tile")
    if not tiles:
        # Try alternate selectors
        tiles = soup.select("[data-pid]") or soup.select(".product-card")

    for tile in tiles:
        try:
            # Extract name - ASICS uses various name selectors
            name = ""
            name_el = (
                tile.select_one(".product-name") or
                tile.select_one(".product-tile__text") or
                tile.select_one("[class*='product-name']") or
                tile.select_one("h2") or
                tile.select_one("h3")
            )
            if name_el:
                name = name_el.get_text(strip=True)

            if not name:
                continue

            # Extract price
            price_text = ""
            price_el = (
                tile.select_one(".price-sales") or
                tile.select_one(".sales-price") or
                tile.select_one("[class*='price']")
            )
            if price_el:
                text = price_el.get_text(strip=True)
                match = re.search(r"\$[\d,]+(?:\.\d{2})?", text)
                if match:
                    price_text = match.group(0)

            # Extract original price
            original_price = ""
            orig_el = tile.select_one(".price-standard") or tile.select_one("[class*='was']")
            if orig_el:
                text = orig_el.get_text(strip=True)
                match = re.search(r"\$[\d,]+(?:\.\d{2})?", text)
                if match:
                    original_price = match.group(0)

            # Extract link
            link = ""
            link_el = tile.select_one(".product-tile__link") or tile.select_one("a[href]")
            if link_el:
                href = link_el.get("href", "")
                if href.startswith("http"):
                    link = href
                elif href.startswith("/"):
                    link = BASE_URL + href

            # Extract image
            image = ""
            img_el = tile.select_one("img[src], img[data-src]")
            if img_el:
                image = img_el.get("src") or img_el.get("data-src") or ""
                if image.startswith("//"):
                    image = "https:" + image

            products.append({
                "name": name,
                "price": price_text,
                "original_price": original_price,
                "link": link,
                "image": image,
            })

        except Exception as e:
            print(f"Error parsing ASICS tile: {e}")
            continue

    return products


def fetch_asics_page(category_id: str, start: int = 0, page_size: int = 48) -> Optional[str]:
    """
    Fetch a page of ASICS products using the Search-UpdateGrid API.
    """
    session = _get_session()

    # Update headers for AJAX request
    session.headers.update({
        "Accept": "text/html, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{BASE_URL}/us/en-us/mens-running-shoes/c/{category_id}/",
    })

    params = {
        "cgid": category_id,
        "start": start,
        "sz": page_size,
    }

    try:
        response = session.get(API_URL, params=params, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Error fetching ASICS API page (start={start}): {e}")
        _reset_session()
        return None


def fetch_category_page(url: str, page_size: int = 350) -> Optional[str]:
    """
    Fetch a full ASICS category page with all products.
    """
    session = _get_session()

    # Add pagination params to get all products
    if "?" in url:
        full_url = f"{url}&start=0&sz={page_size}"
    else:
        full_url = f"{url}?start=0&sz={page_size}"

    try:
        response = session.get(full_url, timeout=60)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Error fetching ASICS category page: {e}")
        _reset_session()
        return None


def parse_json_ld_product(product: dict, gender: str) -> Optional[AsicsProduct]:
    """Parse a JSON-LD product into an AsicsProduct."""
    name = product.get("name", "")
    if not name:
        return None

    offers = product.get("offers", {})
    price = offers.get("price") or offers.get("lowPrice")

    if not price:
        return None

    try:
        price_val = float(price)
        price_str = f"${price_val:.2f}"
    except (ValueError, TypeError):
        return None

    high_price = offers.get("highPrice")
    list_price_str = price_str
    on_sale = False
    if high_price:
        try:
            high_val = float(high_price)
            if high_val > price_val:
                list_price_str = f"${high_val:.2f}"
                on_sale = True
        except (ValueError, TypeError):
            pass

    model = name.strip()
    if not model.upper().startswith("ASICS"):
        model = f"ASICS {model}"

    return AsicsProduct(
        brand="ASICS",
        model=model,
        price=price_str,
        list_price=list_price_str,
        image=product.get("image", ""),
        link=product.get("url", ""),
        gender=gender,
        on_sale=on_sale,
    )


def parse_html_product(data: dict, gender: str) -> Optional[AsicsProduct]:
    """Parse a raw product dict from HTML into an AsicsProduct."""
    name = data.get("name", "")
    if not name:
        return None

    price = data.get("price", "")
    if not price:
        return None

    original_price = data.get("original_price", "")
    on_sale = bool(original_price)

    model = name.strip()
    if not model.upper().startswith("ASICS"):
        model = f"ASICS {model}"

    return AsicsProduct(
        brand="ASICS",
        model=model,
        price=price,
        list_price=original_price if on_sale else price,
        image=data.get("image", ""),
        link=data.get("link", ""),
        gender=gender,
        on_sale=on_sale,
    )


def scrape_asics_category(category_key: str, max_pages: int = 10) -> list[AsicsProduct]:
    """
    Scrape all products from an ASICS category.

    Tries multiple approaches:
    1. SFCC Search-UpdateGrid API
    2. Full category page with HTML parsing
    """
    category_id = CATEGORY_IDS.get(category_key, "aa10201000")
    category_url = CATEGORY_URLS.get(category_key, "")
    gender = "Men's" if category_key == "mens" else "Women's"

    all_products: dict[str, AsicsProduct] = {}

    print(f"Scraping ASICS {category_key} running shoes...")

    # Approach 1: Try SFCC API with pagination
    start = 0
    page_size = 48
    page = 1
    api_worked = False

    while page <= max_pages:
        html = fetch_asics_page(category_id, start=start, page_size=page_size)
        if not html or len(html) < 500:
            break

        # Check if it's a valid product response
        if "product-tile" not in html.lower() and "product" not in html.lower():
            break

        api_worked = True
        raw_products = _extract_products_from_html(html)

        if not raw_products:
            break

        new_count = 0
        for raw in raw_products:
            product = parse_html_product(raw, gender)
            if product:
                key = product.model.lower()
                if key not in all_products:
                    all_products[key] = product
                    new_count += 1
                else:
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
        time.sleep(1.5)

    # Approach 2: Try full category page
    if not api_worked and category_url:
        print(f"  API unavailable, trying category page...")
        html = fetch_category_page(category_url)

        if html:
            # Try JSON-LD
            json_ld_products = _extract_json_ld_products(html)
            if json_ld_products:
                print(f"  Found {len(json_ld_products)} products via JSON-LD")
                for prod_data in json_ld_products:
                    product = parse_json_ld_product(prod_data, gender)
                    if product:
                        key = product.model.lower()
                        if key not in all_products:
                            all_products[key] = product

            # Also try HTML parsing
            html_products = _extract_products_from_html(html)
            if html_products:
                print(f"  Found {len(html_products)} products via HTML parsing")
                for raw in html_products:
                    product = parse_html_product(raw, gender)
                    if product:
                        key = product.model.lower()
                        if key not in all_products:
                            all_products[key] = product

    products = list(all_products.values())
    print(f"Scraped {len(products)} unique {category_key} shoes from ASICS")
    return products


def scrape_asics_all() -> list[dict]:
    """Scrape both men's and women's running shoes from ASICS."""
    all_shoes = []

    for category in ["mens", "womens"]:
        products = scrape_asics_category(category)
        all_shoes.extend([p.to_dict() for p in products])
        time.sleep(2)

    return all_shoes


def scrape_asics() -> list[dict]:
    """
    Main entry point matching existing scraper interface.

    Returns list of shoe dicts compatible with existing add_shoes_to_db().
    """
    print("Scraping ASICS...")
    shoes = scrape_asics_all()
    print(f"Scraped {len(shoes)} total shoes from ASICS")
    return shoes


if __name__ == "__main__":
    shoes = scrape_asics()
    print(f"\nScraped {len(shoes)} shoes total")

    for shoe in shoes[:10]:
        print(f"  {shoe['brand']} - {shoe['model']}: {shoe['price']}")
