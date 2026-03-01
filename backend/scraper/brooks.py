from driver_setup import get_chrome_driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re


def scroll_to_bottom(driver, pause_time=3, max_scrolls=5):
    last_height = driver.execute_script("return document.body.scrollHeight")
    scrolls = 0
    while scrolls < max_scrolls:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause_time)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
        scrolls += 1


def scrape_brooks():
    url = "https://www.brooksrunning.com/en_us/mens-running-shoes/"
    driver = get_chrome_driver()
    driver.set_page_load_timeout(30)
    driver.get(url)

    # Wait for the page to begin rendering product content
    time.sleep(6)

    # Dismiss any cookie/consent banner if present
    try:
        WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree')]")
            )
        ).click()
        time.sleep(1)
    except Exception:
        pass

    # Scroll to trigger lazy-loading of additional product tiles
    scroll_to_bottom(driver, pause_time=3, max_scrolls=5)

    shoes = []
    seen_links = set()

    # Brooks Running (SFCC / SFRA) uses BEM-style class names with an "m-" module prefix.
    # The product tile container class is "m-product-tile".  We try that first, then fall
    # back to broader attribute-based selectors used by some SFCC storefronts.
    tile_selectors = [
        (By.CSS_SELECTOR, "div.m-product-tile"),
        (By.CSS_SELECTOR, "[class*='product-tile']:not([class*='product-tile__'])"),
        (By.CSS_SELECTOR, "li.product-tile"),
        (By.CSS_SELECTOR, "div[class*='product-tile']"),
    ]

    products = []
    for by, selector in tile_selectors:
        try:
            elements = driver.find_elements(by, selector)
            if elements:
                products = elements
                print(f"Brooks: found {len(products)} tiles with selector '{selector}'")
                break
        except Exception:
            continue

    if not products:
        print("Brooks: no product tiles found — attempting JSON-LD extraction fallback.")
        driver.quit()
        return _extract_from_jsonld(url)

    for product in products:
        try:
            # --- Product name ---
            # Try BEM sub-element classes first, then generic heading tags.
            name = None
            for name_selector in [
                ".m-product-tile__name",
                ".m-product-tile__title",
                ".product-tile__name",
                ".product-name",
                "h2", "h3", "h4",
            ]:
                try:
                    name = product.find_element(By.CSS_SELECTOR, name_selector).text.strip()
                    if name:
                        break
                except Exception:
                    continue

            if not name:
                continue

            # --- Price ---
            price = None
            for price_selector in [
                ".m-product-tile__price",
                ".product-tile__price",
                ".price-sales",
                ".sales",
                "[class*='price']",
            ]:
                try:
                    raw = product.find_element(By.CSS_SELECTOR, price_selector).text.strip()
                    # Keep only the first price if a range is shown (e.g. "$130 - $160")
                    match = re.search(r"\$[\d,]+(?:\.\d{1,2})?", raw)
                    if match:
                        price = match.group(0)
                        break
                except Exception:
                    continue

            if not price:
                price = "N/A"

            # --- Product link ---
            link = None
            try:
                # Prefer a dedicated tile-link anchor; fall back to first <a> in tile.
                for link_selector in [
                    ".m-product-tile__link",
                    ".product-tile__link",
                    "a.product-tile__image-link",
                    "a",
                ]:
                    try:
                        href = product.find_element(By.CSS_SELECTOR, link_selector).get_attribute("href")
                        if href and "brooksrunning.com" in href:
                            link = href
                            break
                        elif href and href.startswith("/"):
                            link = "https://www.brooksrunning.com" + href
                            break
                    except Exception:
                        continue
            except Exception:
                pass

            if not link or link in seen_links:
                continue
            seen_links.add(link)

            # --- Product image ---
            img = None
            try:
                # Scroll the tile into view to ensure lazy images are loaded
                driver.execute_script("arguments[0].scrollIntoView();", product)
                for img_selector in [
                    ".m-product-tile__image img",
                    ".product-tile__image img",
                    "img[src*='demandware']",
                    "img",
                ]:
                    try:
                        img_el = product.find_element(By.CSS_SELECTOR, img_selector)
                        src = img_el.get_attribute("src") or img_el.get_attribute("data-src")
                        if src and ("brooksrunning.com" in src or "demandware" in src):
                            img = src
                            break
                        elif src:
                            img = src
                            break
                    except Exception:
                        continue
            except Exception:
                pass

            shoes.append({
                "brand": "Brooks",
                "model": "Brooks " + name if not name.lower().startswith("brooks") else name,
                "price": price,
                "image": img,
                "link": link,
                "retailer": "Brooks",
            })

        except Exception:
            continue

    driver.quit()
    print(f"Brooks: scraped {len(shoes)} shoes.")
    return shoes


def _extract_from_jsonld(url="https://www.brooksrunning.com/en_us/mens-running-shoes/"):
    """
    Fallback: re-fetch the page with requests and extract product URLs from
    the JSON-LD ItemList that SFCC injects server-side.  Returns a minimal
    list of shoe dicts (no price / image — those require JS rendering).
    """
    try:
        import requests, json
        from bs4 import BeautifulSoup

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        shoes = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if data.get("@type") == "ItemList":
                    for item in data.get("itemListElement", []):
                        item_url = item.get("url", "")
                        if not item_url:
                            continue
                        # Derive a human-readable name from the URL slug
                        slug = item_url.rstrip("/").split("/")[-2] if "/" in item_url else item_url
                        name = slug.replace("-", " ").title()
                        shoes.append({
                            "brand": "Brooks",
                            "model": "Brooks " + name,
                            "price": "N/A",
                            "image": None,
                            "link": item_url if item_url.startswith("http") else "https://www.brooksrunning.com" + item_url,
                            "retailer": "Brooks",
                        })
            except Exception:
                continue
        print(f"Brooks JSON-LD fallback: found {len(shoes)} products.")
        return shoes
    except Exception as e:
        print(f"Brooks JSON-LD fallback failed: {e}")
        return []


if __name__ == "__main__":
    results = scrape_brooks()
    for shoe in results:
        print(shoe)
    print(f"Total: {len(results)}")
