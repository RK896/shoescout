"""
Brooks Running API-based scraper.

Uses the Salesforce Commerce Cloud (SFCC) Search-UpdateGrid endpoint that returns
HTML fragments with product data embedded in elements and data attributes.

API endpoint:
    GET https://www.brooksrunning.com/on/demandware.store/Sites-BrooksRunning-Site/en_US/Search-UpdateGrid
    Parameters:
        - cgid: Category ID ("mens-shoes" or "womens-shoes")
        - start: Offset for pagination (0, 24, 48, ...)
        - sz: Page size (default 24)

Product data is extracted from:
    - data-pid: Product ID
    - data-cnstrc-item-name: Product name (e.g., "Glycerin 23")
    - .m-product-tile__price: Price element
    - a[href*="/en_us/"]: Product link
    - img[src*="demandware"]: Product image
"""
import re
import time
from dataclasses import dataclass
from typing import Optional

import requests
from bs4 import BeautifulSoup


@dataclass
class BrooksProduct:
    """Represents a scraped Brooks Running product."""
    brand: str
    model: str
    price: str
    list_price: str
    image: str
    link: str
    gender: str
    on_sale: bool
    retailer: str = "Brooks"

    def to_dict(self) -> dict:
        return {
            "brand": self.brand,
            "model": self.model,
            "price": self.price,
            "image": self.image,
            "link": self.link,
            "retailer": self.retailer,
        }


BASE_URL = "https://www.brooksrunning.com"
API_URL = f"{BASE_URL}/on/demandware.store/Sites-BrooksRunning-Site/en_US/Search-UpdateGrid"

# Category IDs for scraping
CATEGORIES = {
    "mens": "mens-shoes",
    "womens": "womens-shoes",
}

# Global session - initialized lazily
_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    """
    Get or create a requests session with valid Brooks cookies.

    The session is initialized by visiting the Brooks site to obtain
    session cookies automatically.
    """
    global _session

    if _session is not None:
        return _session

    print("Initializing Brooks session...")
    _session = requests.Session()
    _session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })

    # Visit main page to get session cookies
    try:
        _session.get(f"{BASE_URL}/en_us/", timeout=30)
    except requests.RequestException as e:
        print(f"Warning: Failed to initialize Brooks session: {e}")

    # Update headers for API requests
    _session.headers.update({
        "Accept": "text/html, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{BASE_URL}/en_us/mens-running-shoes/",
    })

    return _session


def _reset_session() -> None:
    """Reset the session to force re-initialization on next request."""
    global _session
    _session = None


def fetch_brooks_page(category: str, start: int = 0, page_size: int = 24) -> Optional[str]:
    """
    Fetch a page of Brooks products using the Search-UpdateGrid API.

    Args:
        category: Category ID (e.g., "mens-shoes", "womens-shoes")
        start: Pagination offset
        page_size: Number of products per page

    Returns:
        HTML content as string, or None on error
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
        print(f"Error fetching Brooks page (start={start}): {e}")
        _reset_session()  # Reset session on error
        return None


def extract_products(html: str) -> list[dict]:
    """
    Extract product data from Brooks HTML response.

    Args:
        html: HTML content from Search-UpdateGrid API

    Returns:
        List of raw product dicts
    """
    soup = BeautifulSoup(html, "html.parser")
    products = []

    # Find all product tiles
    tiles = soup.select("[data-pid]")

    for tile in tiles:
        try:
            pid = tile.get("data-pid", "")
            name = tile.get("data-cnstrc-item-name", "")

            if not pid or not name:
                continue

            # Extract price - check for sale price first
            price_text = ""
            price_el = tile.select_one(".m-product-tile__price, .pricing__sale, .js-sale-price")
            if price_el:
                price_text = price_el.text.strip()
                # Extract first price if multiple shown
                match = re.search(r"\$[\d,]+(?:\.\d{2})?", price_text)
                if match:
                    price_text = match.group(0)

            # Check for original/strikethrough price (indicates sale)
            original_price = ""
            strike_el = tile.select_one(".pricing__strikethrough, [class*=strikethrough], del, s")
            if strike_el:
                match = re.search(r"\$[\d,]+(?:\.\d{2})?", strike_el.text.strip())
                if match:
                    original_price = match.group(0)

            # Extract link
            link = ""
            link_el = tile.select_one("a[href*='/en_us/']")
            if link_el:
                href = link_el.get("href", "")
                if href.startswith("http"):
                    link = href
                elif href.startswith("/"):
                    link = BASE_URL + href
                else:
                    link = href

            # Extract image
            image = ""
            img_el = tile.select_one("img[src*='demandware'], img[src*='brooksrunning']")
            if img_el:
                image = img_el.get("src", "") or img_el.get("data-src", "")

            products.append({
                "pid": pid,
                "name": name,
                "price": price_text,
                "original_price": original_price,
                "link": link,
                "image": image,
            })

        except Exception as e:
            print(f"Error parsing Brooks product: {e}")
            continue

    return products


def parse_product(data: dict, gender: str) -> Optional[BrooksProduct]:
    """
    Parse a raw product dict into a BrooksProduct.

    Args:
        data: Raw product dict from extract_products
        gender: "Men's" or "Women's"

    Returns:
        BrooksProduct or None if product should be skipped
    """
    name = data.get("name", "")
    if not name:
        return None

    price = data.get("price", "")
    if not price:
        return None

    original_price = data.get("original_price", "")
    on_sale = bool(original_price)

    # Format model name with brand
    model = f"Brooks {name}"

    return BrooksProduct(
        brand="Brooks",
        model=model,
        price=price,
        list_price=original_price if on_sale else price,
        image=data.get("image", ""),
        link=data.get("link", ""),
        gender=gender,
        on_sale=on_sale,
    )


def scrape_brooks_category(category_key: str, max_pages: int = 10) -> list[BrooksProduct]:
    """
    Scrape all products from a Brooks category.

    Args:
        category_key: "mens" or "womens"
        max_pages: Maximum pages to fetch

    Returns:
        List of BrooksProduct objects
    """
    category = CATEGORIES.get(category_key, "mens-shoes")
    gender = "Men's" if category_key == "mens" else "Women's"

    all_products: dict[str, BrooksProduct] = {}  # Dedupe by model
    start = 0
    page_size = 24
    page = 1

    print(f"Scraping Brooks {category_key} shoes...")

    while page <= max_pages:
        html = fetch_brooks_page(category, start=start, page_size=page_size)
        if not html:
            break

        raw_products = extract_products(html)

        if not raw_products:
            print(f"  Page {page}: no products found, stopping")
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
                    # Keep the one with lower price
                    existing = all_products[key]
                    try:
                        existing_price = float(existing.price.replace("$", "").replace(",", ""))
                        new_price = float(product.price.replace("$", "").replace(",", ""))
                        if new_price < existing_price:
                            all_products[key] = product
                    except ValueError:
                        pass

        print(f"  Page {page}: {len(raw_products)} products, {new_count} new unique")

        # Check if we've fetched all products
        if len(raw_products) < page_size:
            print(f"  Reached end of results")
            break

        start += page_size
        page += 1
        time.sleep(1.5)  # Polite delay

    products = list(all_products.values())
    print(f"Scraped {len(products)} unique {category_key} shoes from Brooks")
    return products


def scrape_brooks_all() -> list[dict]:
    """
    Scrape both men's and women's shoes.

    Returns:
        List of shoe dicts
    """
    all_shoes = []

    for category in ["mens", "womens"]:
        products = scrape_brooks_category(category)
        all_shoes.extend([p.to_dict() for p in products])
        time.sleep(2)  # Polite delay between categories

    return all_shoes


def scrape_brooks() -> list[dict]:
    """
    Main entry point matching existing scraper interface.

    Returns list of shoe dicts compatible with existing add_shoes_to_db().
    Scrapes both men's and women's shoes.
    """
    print("Scraping Brooks Running...")
    shoes = scrape_brooks_all()
    print(f"Scraped {len(shoes)} total shoes from Brooks")
    return shoes


if __name__ == "__main__":
    # Test run
    shoes = scrape_brooks()
    print(f"\nScraped {len(shoes)} shoes total")

    # Print sample
    for shoe in shoes[:10]:
        print(f"  {shoe['brand']} - {shoe['model']}: {shoe['price']}")
