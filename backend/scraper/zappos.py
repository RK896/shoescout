from driver_setup import get_chrome_driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re


def scroll_to_bottom(driver, pause_time=2, max_scrolls=8):
    """Scroll down to trigger lazy loading of products."""
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


def scrape_zappos():
    """Scrape men's running shoes from Zappos."""
    url = "https://www.zappos.com/men-running-shoes"
    driver = get_chrome_driver()
    driver.set_page_load_timeout(30)

    try:
        driver.get(url)
        time.sleep(5)

        # Dismiss any cookie/popup banners
        try:
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'close')]")
                )
            ).click()
            time.sleep(1)
        except Exception:
            pass

        # Scroll to load more products (Zappos uses infinite scroll or lazy loading)
        scroll_to_bottom(driver, pause_time=2, max_scrolls=8)

        shoes = []
        seen_links = set()

        # Zappos uses article tags or product card containers
        product_selectors = [
            (By.CSS_SELECTOR, "article[data-product-id]"),
            (By.CSS_SELECTOR, "[data-product-id]"),
            (By.CSS_SELECTOR, ".product-card"),
            (By.CSS_SELECTOR, "[class*='productCard']"),
            (By.CSS_SELECTOR, "article"),
        ]

        products = []
        for by, selector in product_selectors:
            try:
                elements = driver.find_elements(by, selector)
                if elements and len(elements) > 5:
                    products = elements
                    print(f"Zappos: found {len(products)} products with selector '{selector}'")
                    break
            except Exception:
                continue

        if not products:
            print("Zappos: no products found with standard selectors, trying fallback")
            # Try a more generic approach - look for links with product structure
            products = driver.find_elements(By.CSS_SELECTOR, "a[href*='/product/']")
            products = list(set(products))[:100]  # Dedupe and limit

        for product in products:
            try:
                # --- Product link ---
                link = None
                try:
                    if product.tag_name == "a":
                        link = product.get_attribute("href")
                    else:
                        link_el = product.find_element(By.CSS_SELECTOR, "a[href*='/product/'], a[href*='/p/']")
                        link = link_el.get_attribute("href")
                except Exception:
                    try:
                        link_el = product.find_element(By.TAG_NAME, "a")
                        link = link_el.get_attribute("href")
                    except Exception:
                        continue

                if not link or link in seen_links:
                    continue
                if "zappos.com" not in link and not link.startswith("/"):
                    continue
                seen_links.add(link)

                # --- Product name / Brand extraction ---
                name = None
                brand = None

                # Zappos typically shows brand name and product name separately
                for brand_selector in [
                    "[data-brand-name]",
                    "[class*='brand']",
                    ".Ax-z",  # Zappos uses utility classes
                    "span:first-child",
                ]:
                    try:
                        brand_el = product.find_element(By.CSS_SELECTOR, brand_selector)
                        brand_text = brand_el.get_attribute("data-brand-name") or brand_el.text.strip()
                        if brand_text and len(brand_text) < 50:
                            brand = brand_text
                            break
                    except Exception:
                        continue

                for name_selector in [
                    "[data-product-name]",
                    "[class*='productName']",
                    "[class*='product-name']",
                    "p", "span", "div",
                ]:
                    try:
                        name_el = product.find_element(By.CSS_SELECTOR, name_selector)
                        name_text = name_el.get_attribute("data-product-name") or name_el.text.strip()
                        if name_text and len(name_text) > 3 and len(name_text) < 150:
                            name = name_text
                            break
                    except Exception:
                        continue

                # Fallback: extract from aria-label or alt text
                if not name:
                    try:
                        name = product.get_attribute("aria-label") or ""
                        if not name:
                            img = product.find_element(By.TAG_NAME, "img")
                            name = img.get_attribute("alt") or ""
                    except Exception:
                        pass

                # Fallback: extract product name from URL (e.g., /p/nike-air-zoom-pegasus/...)
                bad_patterns = ["favorites", "these are ads", "clicking an ad", "you'll find"]
                name_is_bad = not name or len(name) < 5 or any(p in name.lower() for p in bad_patterns)
                if name_is_bad:
                    try:
                        # Parse product name from URL like /p/brand-model-name/product/123
                        url_parts = link.split("/p/")
                        if len(url_parts) > 1:
                            slug = url_parts[1].split("/")[0]
                            name = slug.replace("-", " ").title()
                    except Exception:
                        pass

                if not name or len(name) < 5:
                    continue

                # Extract brand from product name
                known_brands = ["Nike", "Brooks", "HOKA", "Hoka", "Saucony", "ASICS", "Asics",
                                "New Balance", "Adidas", "On", "Altra", "Mizuno", "Salomon",
                                "Topo", "Merrell", "Karhu", "Puma", "Reebok", "Under Armour",
                                "361", "Newton", "Diadora", "Craft", "Norda"]
                if not brand or "favorites" in brand.lower():
                    brand = None
                    for kb in known_brands:
                        if kb.lower() in name.lower():
                            brand = kb
                            break
                    if not brand:
                        parts = name.split()
                        brand = parts[0] if parts else "Unknown"

                # --- Price ---
                price = None
                for price_selector in [
                    "[data-price]",
                    "[class*='price']",
                    "[class*='Price']",
                    "span[class*='price']",
                ]:
                    try:
                        price_el = product.find_element(By.CSS_SELECTOR, price_selector)
                        raw = price_el.get_attribute("data-price") or price_el.text.strip()
                        match = re.search(r"\$[\d,]+(?:\.\d{1,2})?", raw)
                        if match:
                            price = match.group(0)
                            break
                    except Exception:
                        continue

                if not price:
                    # Look for price anywhere in the product text
                    try:
                        text = product.text
                        match = re.search(r"\$[\d,]+(?:\.\d{1,2})?", text)
                        if match:
                            price = match.group(0)
                    except Exception:
                        pass

                if not price:
                    price = "N/A"

                # --- Product image ---
                img_url = None
                try:
                    img_el = product.find_element(By.TAG_NAME, "img")
                    img_url = img_el.get_attribute("src") or img_el.get_attribute("data-src")
                except Exception:
                    pass

                shoes.append({
                    "brand": brand or "Unknown",
                    "model": name,
                    "price": price,
                    "image": img_url,
                    "link": link if link.startswith("http") else f"https://www.zappos.com{link}",
                    "retailer": "Zappos"
                })

            except Exception as e:
                print(f"Zappos: skipping product due to error: {e}")
                continue

        driver.quit()
        print(f"Zappos: scraped {len(shoes)} shoes")
        return shoes

    except Exception as e:
        print(f"Zappos scraper failed: {e}")
        driver.quit()
        return []


if __name__ == "__main__":
    results = scrape_zappos()
    for shoe in results[:10]:
        print(shoe)
    print(f"Total: {len(results)} shoes")
