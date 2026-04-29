"""
ON Running scraper using sitemap and product page extraction.

ON Running uses a Nuxt.js frontend that loads products dynamically. This scraper:
1. Fetches the products sitemap to get all product URLs
2. Filters for running shoes (Cloud*, Cloudsurfer, Cloudmonster, etc.)
3. Groups by base model to avoid color duplicates
4. Fetches individual product pages for pricing via JSON-LD structured data

Key features:
- No JavaScript required - uses sitemap + JSON-LD
- Deduplicates by model name, keeping lowest price
- Handles both men's and women's shoes
"""
import json
import re
import time
from dataclasses import dataclass
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup


@dataclass
class OnProduct:
    """Represents a scraped ON Running product."""
    brand: str
    model: str
    price: str
    list_price: str
    image: str
    link: str
    gender: str
    retailer: str = "ON"

    def to_dict(self) -> dict:
        return {
            "brand": self.brand,
            "model": self.model,
            "price": self.price,
            "image": self.image,
            "link": self.link,
            "retailer": self.retailer,
        }


BASE_URL = "https://www.on.com"

# Try these sitemaps in order
SITEMAP_URLS = [
    f"{BASE_URL}/en-us/products.xml",
    f"{BASE_URL}/sitemap.xml",
    f"{BASE_URL}/en-us/sitemap.xml",
]

# Category pages to fall back to if sitemap finds nothing
CATEGORY_URLS = [
    f"{BASE_URL}/en-us/running/men/shoes",
    f"{BASE_URL}/en-us/running/women/shoes",
    f"{BASE_URL}/en-us/men/running/shoes",
    f"{BASE_URL}/en-us/women/running/shoes",
]

# Running shoe model keywords (all lowercase)
RUNNING_SHOE_KEYWORDS = [
    "cloud-5", "cloud-6", "cloud-x", "cloud5", "cloud6", "cloudx",
    "cloudboom", "cloudmonster", "cloudstratus", "cloudflow",
    "cloudrunner", "cloudvista", "cloudventure", "cloudultra",
    "cloudgo", "cloudeclipse", "cloudsurfer", "cloudtilt",
    "cloudswift", "cloudrush", "cloudace", "cloudflyer",
    "cloudspike", "cloudzone", "cloudhero", "cloud",
]

# Global session
_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    """Get or create a requests session with proper headers."""
    global _session

    if _session is not None:
        return _session

    _session = requests.Session()
    _session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    })

    return _session


def _reset_session() -> None:
    """Reset the session."""
    global _session
    _session = None


def fetch_sitemap() -> list[str]:
    """
    Fetch product URLs from ON Running sitemap.

    Tries multiple sitemap URLs and handles sitemap index files.
    Returns list of product page URLs.
    """
    session = _get_session()
    all_urls: list[str] = []

    for sitemap_url in SITEMAP_URLS:
        try:
            response = session.get(sitemap_url, timeout=60)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"  Sitemap {sitemap_url} failed: {e}")
            continue

        content = response.text

        # If it's a sitemap index, find product sub-sitemaps
        if "<sitemapindex" in content:
            sub_urls = re.findall(r'<loc>(https://www\.on\.com[^<]*)</loc>', content)
            for sub_url in sub_urls:
                if "product" in sub_url.lower() or "shop" in sub_url.lower():
                    try:
                        sub_resp = session.get(sub_url, timeout=60)
                        sub_resp.raise_for_status()
                        found = re.findall(r'<loc>(https://www\.on\.com/en-us/[^<]+)</loc>', sub_resp.text)
                        all_urls.extend(found)
                    except requests.RequestException:
                        pass
            if all_urls:
                print(f"  Found {len(all_urls)} URLs from sitemap index")
                return all_urls
        else:
            # Try product URL patterns from most to least specific
            for pattern in [
                r'<loc>(https://www\.on\.com/en-us/products/[^<]+)</loc>',
                r'<loc>(https://www\.on\.com/en-us/[^<]+-shoes[^<]*)</loc>',
                r'<loc>(https://www\.on\.com/en-us/[^<]+)</loc>',
            ]:
                found = re.findall(pattern, content)
                if found:
                    print(f"  Found {len(found)} URLs from {sitemap_url}")
                    return found

    return all_urls


def filter_running_shoes(urls: list[str]) -> list[str]:
    """
    Filter URLs to only include running shoe pages.

    Accepts URLs containing "shoes" (with or without dashes) and
    at least one Cloud model keyword.
    """
    running_shoes = []
    for url in urls:
        url_lower = url.lower()
        # Accept URLs that contain "shoes" anywhere
        if "shoe" not in url_lower:
            continue
        # Must also contain a running shoe keyword
        if any(kw in url_lower for kw in RUNNING_SHOE_KEYWORDS):
            running_shoes.append(url)
    return running_shoes


def extract_model_key(url: str) -> str:
    """
    Extract base model name from URL for deduplication.

    Example: /products/cloudmonster-3-m-3mg1111/mens/black-eclipse-shoes-3MG11110106
    Returns: cloudmonster-3-m (ignoring color variants)
    """
    # Extract the model part from the URL path
    match = re.search(r'/products/([^/]+)/', url)
    if match:
        return match.group(1).lower()
    return url


def group_urls_by_model(urls: list[str]) -> dict[str, list[str]]:
    """
    Group URLs by base model to avoid fetching all color variants.

    Args:
        urls: List of product URLs

    Returns:
        Dict mapping model key to list of URLs
    """
    groups: dict[str, list[str]] = {}
    for url in urls:
        key = extract_model_key(url)
        if key not in groups:
            groups[key] = []
        groups[key].append(url)
    return groups


def fetch_product_page(url: str) -> Optional[dict]:
    """
    Fetch a product page and extract product data from JSON-LD.

    Args:
        url: Product page URL

    Returns:
        Product data dict or None
    """
    session = _get_session()

    try:
        response = session.get(url, timeout=15)
        response.raise_for_status()
    except requests.RequestException:
        return None

    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    # Look for JSON-LD structured data
    json_ld_scripts = soup.find_all("script", type="application/ld+json")

    for script in json_ld_scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get("@type") == "Product":
                return {
                    "name": data.get("name", ""),
                    "url": url,
                    "image": data.get("image", ""),
                    "offers": data.get("offers", {}),
                    "brand": data.get("brand", {}).get("name", "ON"),
                }
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        return {
                            "name": item.get("name", ""),
                            "url": url,
                            "image": item.get("image", ""),
                            "offers": item.get("offers", {}),
                            "brand": item.get("brand", {}).get("name", "ON"),
                        }
        except (json.JSONDecodeError, TypeError):
            continue

    # Fallback: Try to extract from meta tags
    og_title = soup.find("meta", property="og:title")
    og_image = soup.find("meta", property="og:image")
    og_price = soup.find("meta", property="product:price:amount")

    if og_title:
        name = og_title.get("content", "")
        image = og_image.get("content", "") if og_image else ""
        price = og_price.get("content", "") if og_price else ""

        return {
            "name": name,
            "url": url,
            "image": image,
            "offers": {"price": price} if price else {},
            "brand": "ON",
        }

    return None


def parse_product(data: dict) -> Optional[OnProduct]:
    """
    Parse raw product data into an OnProduct.

    Args:
        data: Raw product dict

    Returns:
        OnProduct or None if invalid
    """
    name = data.get("name", "")
    if not name:
        return None

    # Determine gender from URL or name
    url = data.get("url", "")
    if "/mens/" in url.lower() or "men's" in name.lower():
        gender = "Men's"
    elif "/womens/" in url.lower() or "women's" in name.lower():
        gender = "Women's"
    else:
        gender = "Unisex"

    # Extract price
    offers = data.get("offers", {})
    price = ""
    list_price = ""

    if isinstance(offers, dict):
        price_val = offers.get("price") or offers.get("lowPrice") or offers.get("minPrice")
        list_val = offers.get("highPrice") or offers.get("maxPrice") or price_val

        if price_val:
            try:
                price = f"${float(price_val):.2f}"
            except (ValueError, TypeError):
                price = str(price_val) if price_val else ""

        if list_val:
            try:
                list_price = f"${float(list_val):.2f}"
            except (ValueError, TypeError):
                list_price = str(list_val) if list_val else ""
    elif isinstance(offers, list) and offers:
        # Take first offer
        first_offer = offers[0]
        price_val = first_offer.get("price")
        if price_val:
            try:
                price = f"${float(price_val):.2f}"
                list_price = price
            except (ValueError, TypeError):
                pass

    if not price:
        return None

    # Clean up model name - add brand prefix if needed
    model = name.strip()
    # Remove color from model name if present
    model = re.sub(r'\s*-\s*(Black|White|Grey|Blue|Red|Green|Yellow|Orange|Purple|Pink|Sand|Olive|Navy|Ice|Ivory|Eclipse|Pearl|Midnight|Seedling|Malibu|Mineral|Arctic|Lilac|Limelight|Grenadine|Raspberry).*$', '', model, flags=re.IGNORECASE)

    if not model.lower().startswith("on "):
        model = f"ON {model}"

    # Get image URL
    image = data.get("image", "")
    if isinstance(image, list):
        image = image[0] if image else ""

    return OnProduct(
        brand="ON",
        model=model,
        price=price,
        list_price=list_price or price,
        image=image,
        link=url,
        gender=gender,
    )


def _extract_urls_from_category_page(url: str) -> list[str]:
    """Extract product URLs from an ON Running category page."""
    session = _get_session()
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException:
        return []

    # Look for product links in the HTML
    found = re.findall(r'href="(/en-us/[^"]*shoes[^"]*)"', resp.text)
    urls = [f"{BASE_URL}{path}" for path in found if "cloud" in path.lower()]
    return list(set(urls))


def scrape_on_products(max_models: int = 100, workers: int = 5) -> list[OnProduct]:
    """
    Scrape running shoes from ON Running.

    Args:
        max_models: Maximum number of unique models to scrape
        workers: Number of parallel workers for fetching pages

    Returns:
        List of OnProduct objects
    """
    print("Fetching ON Running sitemap...")
    all_urls = fetch_sitemap()
    print(f"  Found {len(all_urls)} total product URLs")

    # If sitemap yielded nothing, try category pages directly
    if not all_urls:
        print("  Sitemap empty — trying category pages...")
        for cat_url in CATEGORY_URLS:
            cat_urls = _extract_urls_from_category_page(cat_url)
            all_urls.extend(cat_urls)
            print(f"  {cat_url}: {len(cat_urls)} URLs")
        print(f"  Category pages total: {len(all_urls)} URLs")

    # Filter for running shoes
    running_urls = filter_running_shoes(all_urls)
    print(f"  Found {len(running_urls)} running shoe URLs")

    # Group by model to avoid fetching every color variant
    model_groups = group_urls_by_model(running_urls)
    print(f"  Found {len(model_groups)} unique models")

    # Take first URL from each model group (limit to max_models)
    urls_to_fetch = []
    for model_key, urls in list(model_groups.items())[:max_models]:
        urls_to_fetch.append(urls[0])

    print(f"  Fetching {len(urls_to_fetch)} product pages...")

    # Fetch product pages in parallel
    products: dict[str, OnProduct] = {}
    fetched = 0

    def fetch_with_delay(url):
        time.sleep(0.2)  # Small delay to be polite
        return fetch_product_page(url)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_url = {executor.submit(fetch_with_delay, url): url for url in urls_to_fetch}

        for future in as_completed(future_to_url):
            url = future_to_url[future]
            fetched += 1

            try:
                data = future.result()
                if data:
                    product = parse_product(data)
                    if product:
                        key = product.model.lower()
                        if key not in products:
                            products[key] = product
                        else:
                            # Keep lower price
                            try:
                                existing_price = float(products[key].price.replace("$", "").replace(",", ""))
                                new_price = float(product.price.replace("$", "").replace(",", ""))
                                if new_price < existing_price:
                                    products[key] = product
                            except ValueError:
                                pass
            except Exception as e:
                print(f"    Error fetching {url}: {e}")

            if fetched % 20 == 0:
                print(f"    Fetched {fetched}/{len(urls_to_fetch)} pages, {len(products)} products")

    return list(products.values())


def scrape_on() -> list[dict]:
    """
    Main entry point matching existing scraper interface.

    Returns list of shoe dicts compatible with add_shoes_to_db().
    """
    print("Scraping ON Running...")
    products = scrape_on_products(max_models=150)
    print(f"Scraped {len(products)} unique shoes from ON Running")
    return [p.to_dict() for p in products]


if __name__ == "__main__":
    # Test run
    shoes = scrape_on()
    print(f"\nScraped {len(shoes)} shoes total")

    for shoe in shoes[:15]:
        print(f"  {shoe['model']}: {shoe['price']}")
