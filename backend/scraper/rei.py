"""
REI API-based scraper.

REI uses a combination of server-rendered HTML and JSON data embedded in script tags.
This scraper fetches category pages and extracts product data from multiple sources:

1. JSON-LD structured data in script tags
2. __NEXT_DATA__ or similar React/Next.js hydration data
3. Product tiles with data attributes
4. Search API endpoints if available

Category URLs:
    Men's: https://www.rei.com/c/mens-road-running-shoes
    Women's: https://www.rei.com/c/womens-road-running-shoes
"""
import json
import re
import time
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup


@dataclass
class REIProduct:
    """Represents a scraped REI product."""
    brand: str
    model: str
    price: str
    list_price: str
    image: str
    link: str
    gender: str
    on_sale: bool
    retailer: str = "REI"

    def to_dict(self) -> dict:
        return {
            "brand": self.brand,
            "model": self.model,
            "price": self.price,
            "image": self.image,
            "link": self.link,
            "retailer": self.retailer,
        }


BASE_URL = "https://www.rei.com"

# Category pages for running shoes
CATEGORY_URLS = {
    "mens": f"{BASE_URL}/c/mens-road-running-shoes",
    "womens": f"{BASE_URL}/c/womens-road-running-shoes",
}

# Search URL pattern
SEARCH_URL = f"{BASE_URL}/search"

# Global session
_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    """Get or create a requests session with valid REI cookies."""
    global _session

    if _session is not None:
        return _session

    print("Initializing REI session...")
    _session = requests.Session()
    _session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    })

    # Visit main page to get cookies
    try:
        resp = _session.get(BASE_URL, timeout=30)
        print(f"  Session init: status {resp.status_code}")
    except requests.RequestException as e:
        print(f"Warning: Failed to initialize REI session: {e}")

    return _session


def _reset_session() -> None:
    """Reset the session."""
    global _session
    _session = None


def _extract_json_ld_products(html: str) -> list[dict]:
    """Extract products from JSON-LD structured data."""
    soup = BeautifulSoup(html, "html.parser")
    products = []

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)

            # Handle ItemList
            if data.get("@type") == "ItemList":
                for item in data.get("itemListElement", []):
                    product = item.get("item", {})
                    if product.get("@type") == "Product":
                        products.append(product)

            # Handle ProductGroup or Product array
            elif data.get("@type") == "Product":
                products.append(data)

            # Handle array of products
            elif isinstance(data, list):
                for item in data:
                    if item.get("@type") == "Product":
                        products.append(item)

        except (json.JSONDecodeError, TypeError):
            continue

    return products


def _extract_next_data_products(html: str) -> list[dict]:
    """Extract products from __NEXT_DATA__ or similar hydration data."""
    soup = BeautifulSoup(html, "html.parser")
    products = []

    # Look for Next.js data
    next_script = soup.find("script", id="__NEXT_DATA__")
    if next_script:
        try:
            data = json.loads(next_script.string)
            # Navigate through common paths to find products
            props = data.get("props", {}).get("pageProps", {})
            if "products" in props:
                products.extend(props["products"])
            if "searchResults" in props:
                results = props["searchResults"]
                if isinstance(results, dict) and "products" in results:
                    products.extend(results["products"])
        except (json.JSONDecodeError, TypeError):
            pass

    # Look for embedded JSON in other script tags
    for script in soup.find_all("script"):
        if not script.string:
            continue

        # Look for product data patterns
        patterns = [
            r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
            r'window\.pageData\s*=\s*({.+?});',
            r'"products"\s*:\s*(\[.+?\])',
        ]

        for pattern in patterns:
            match = re.search(pattern, script.string, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(1))
                    if isinstance(data, list):
                        products.extend(data)
                    elif isinstance(data, dict):
                        if "products" in data:
                            products.extend(data["products"])
                except (json.JSONDecodeError, TypeError):
                    continue

    return products


def _extract_products_from_html(html: str) -> list[dict]:
    """
    Extract products from REI HTML using CSS selectors.

    REI product cards typically use classes like:
    - .product-card or [data-ui="product-card"]
    - .product-name for titles
    - .price-value for current price
    - .product-image for images
    """
    soup = BeautifulSoup(html, "html.parser")
    products = []

    # Try various product container selectors
    tile_selectors = [
        "[data-ui='product-card']",
        ".product-card",
        "[class*='ProductCard']",
        ".search-results__product",
        "[data-id][class*='product']",
        "li[class*='product']",
    ]

    tiles = []
    for selector in tile_selectors:
        tiles = soup.select(selector)
        if tiles:
            print(f"  Found {len(tiles)} product tiles with selector: {selector}")
            break

    for tile in tiles:
        try:
            # Extract product name
            name = ""
            name_selectors = [
                "[data-ui='product-card-title']",
                ".product-card__title",
                "[class*='ProductCard__title']",
                ".product-name",
                "h2", "h3",
            ]
            for sel in name_selectors:
                name_el = tile.select_one(sel)
                if name_el:
                    name = name_el.get_text(strip=True)
                    if name:
                        break

            if not name:
                continue

            # Extract brand (REI shows brand separately)
            brand = ""
            brand_selectors = [
                "[data-ui='product-card-brand']",
                ".product-card__brand",
                "[class*='brand']",
            ]
            for sel in brand_selectors:
                brand_el = tile.select_one(sel)
                if brand_el:
                    brand = brand_el.get_text(strip=True)
                    if brand:
                        break

            # Extract current price
            price_text = ""
            price_selectors = [
                "[data-ui='product-card-sale-price']",
                "[data-ui='product-card-price']",
                ".price-value",
                "[class*='sale-price']",
                "[class*='price']",
            ]
            for sel in price_selectors:
                price_el = tile.select_one(sel)
                if price_el:
                    text = price_el.get_text(strip=True)
                    match = re.search(r"\$[\d,]+(?:\.\d{2})?", text)
                    if match:
                        price_text = match.group(0)
                        break

            # Extract original/compare price
            original_price = ""
            orig_selectors = [
                "[data-ui='product-card-compare-price']",
                ".price-compare",
                "[class*='compare-price']",
                "[class*='was-price']",
                "del", "s",
            ]
            for sel in orig_selectors:
                orig_el = tile.select_one(sel)
                if orig_el:
                    text = orig_el.get_text(strip=True)
                    match = re.search(r"\$[\d,]+(?:\.\d{2})?", text)
                    if match:
                        original_price = match.group(0)
                        break

            # Extract link
            link = ""
            link_el = tile.select_one("a[href*='/product/']") or tile.select_one("a[href]")
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
                "brand": brand,
                "name": name,
                "price": price_text,
                "original_price": original_price,
                "link": link,
                "image": image,
            })

        except Exception as e:
            print(f"Error parsing REI tile: {e}")
            continue

    return products


def fetch_category_page(url: str, page: int = 1) -> Optional[str]:
    """Fetch an REI category page."""
    session = _get_session()

    # REI uses page parameter for pagination
    if page > 1:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}page={page}"

    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Error fetching REI page: {e}")
        _reset_session()
        return None


def parse_json_ld_product(product: dict, gender: str) -> Optional[REIProduct]:
    """Parse a JSON-LD product into an REIProduct."""
    name = product.get("name", "")
    if not name:
        return None

    # Get brand
    brand_data = product.get("brand", {})
    brand = brand_data.get("name", "") if isinstance(brand_data, dict) else str(brand_data)

    # Get price
    offers = product.get("offers", {})
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    price = offers.get("price") or offers.get("lowPrice")
    if not price:
        return None

    try:
        price_val = float(price)
        price_str = f"${price_val:.2f}"
    except (ValueError, TypeError):
        return None

    # Check for sale
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

    # Format model name
    model = name.strip()
    if brand and not model.lower().startswith(brand.lower()):
        model = f"{brand} {model}"

    return REIProduct(
        brand=brand or "Unknown",
        model=model,
        price=price_str,
        list_price=list_price_str,
        image=product.get("image", ""),
        link=product.get("url", ""),
        gender=gender,
        on_sale=on_sale,
    )


def parse_html_product(data: dict, gender: str) -> Optional[REIProduct]:
    """Parse a raw product dict from HTML into an REIProduct."""
    name = data.get("name", "")
    if not name:
        return None

    price = data.get("price", "")
    if not price:
        return None

    brand = data.get("brand", "")
    original_price = data.get("original_price", "")
    on_sale = bool(original_price)

    # Format model name
    model = name.strip()
    if brand and not model.lower().startswith(brand.lower()):
        model = f"{brand} {model}"

    return REIProduct(
        brand=brand or "Unknown",
        model=model,
        price=price,
        list_price=original_price if on_sale else price,
        image=data.get("image", ""),
        link=data.get("link", ""),
        gender=gender,
        on_sale=on_sale,
    )


def scrape_rei_category(category_key: str, max_pages: int = 5) -> list[REIProduct]:
    """
    Scrape all products from an REI category.

    Tries multiple extraction methods:
    1. JSON-LD structured data
    2. __NEXT_DATA__ hydration data
    3. HTML parsing with CSS selectors
    """
    category_url = CATEGORY_URLS.get(category_key, "")
    gender = "Men's" if category_key == "mens" else "Women's"

    if not category_url:
        print(f"Unknown category: {category_key}")
        return []

    all_products: dict[str, REIProduct] = {}

    print(f"Scraping REI {category_key} running shoes...")

    page = 1
    while page <= max_pages:
        html = fetch_category_page(category_url, page=page)
        if not html:
            break

        found_products = False

        # Try JSON-LD first
        json_ld_products = _extract_json_ld_products(html)
        if json_ld_products:
            print(f"  Page {page}: Found {len(json_ld_products)} products via JSON-LD")
            found_products = True
            for prod_data in json_ld_products:
                product = parse_json_ld_product(prod_data, gender)
                if product:
                    key = product.model.lower()
                    if key not in all_products:
                        all_products[key] = product

        # Try Next.js data
        next_products = _extract_next_data_products(html)
        if next_products:
            print(f"  Page {page}: Found {len(next_products)} products via hydration data")
            found_products = True
            for prod_data in next_products:
                # Next.js data might have different structure
                name = prod_data.get("name") or prod_data.get("title", "")
                brand = prod_data.get("brand", {})
                if isinstance(brand, dict):
                    brand = brand.get("name", "")

                price = prod_data.get("price") or prod_data.get("salePrice") or prod_data.get("displayPrice", "")
                if isinstance(price, (int, float)):
                    price = f"${price:.2f}"

                if name and price:
                    model = f"{brand} {name}" if brand else name
                    product = REIProduct(
                        brand=brand or "Unknown",
                        model=model,
                        price=price if isinstance(price, str) else f"${price}",
                        list_price=prod_data.get("comparePrice", price),
                        image=prod_data.get("image", ""),
                        link=prod_data.get("url", ""),
                        gender=gender,
                        on_sale=bool(prod_data.get("comparePrice")),
                    )
                    key = product.model.lower()
                    if key not in all_products:
                        all_products[key] = product

        # Try HTML parsing
        html_products = _extract_products_from_html(html)
        if html_products:
            print(f"  Page {page}: Found {len(html_products)} products via HTML parsing")
            found_products = True
            for raw in html_products:
                product = parse_html_product(raw, gender)
                if product:
                    key = product.model.lower()
                    if key not in all_products:
                        all_products[key] = product

        if not found_products:
            print(f"  Page {page}: No products found, stopping pagination")
            break

        page += 1
        time.sleep(2)  # Polite delay

    products = list(all_products.values())
    print(f"Scraped {len(products)} unique {category_key} shoes from REI")
    return products


def scrape_rei_all() -> list[dict]:
    """Scrape both men's and women's running shoes from REI."""
    all_shoes = []

    for category in ["mens", "womens"]:
        products = scrape_rei_category(category)
        all_shoes.extend([p.to_dict() for p in products])
        time.sleep(2)

    return all_shoes


def scrape_rei() -> list[dict]:
    """
    Main entry point matching existing scraper interface.

    Returns list of shoe dicts compatible with existing add_shoes_to_db().
    """
    print("Scraping REI...")
    shoes = scrape_rei_all()
    print(f"Scraped {len(shoes)} total shoes from REI")
    return shoes


if __name__ == "__main__":
    shoes = scrape_rei()
    print(f"\nScraped {len(shoes)} shoes total")

    for shoe in shoes[:10]:
        print(f"  {shoe['brand']} - {shoe['model']}: {shoe['price']}")
