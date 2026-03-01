from driver_setup import get_chrome_driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re


def scroll_to_bottom(driver, pause_time=2, max_scrolls=6):
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


def scrape_fleetfeet():
    """Scrape running shoes from Fleet Feet (specialty running store)."""
    url = "https://www.fleetfeet.com/browse/shoes/mens"
    driver = get_chrome_driver()
    driver.set_page_load_timeout(30)

    try:
        driver.get(url)
        time.sleep(6)

        # Dismiss any cookie/popup banners
        try:
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'close') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'got it')]")
                )
            ).click()
            time.sleep(1)
        except Exception:
            pass

        # Try to close any modal overlays
        try:
            close_buttons = driver.find_elements(By.CSS_SELECTOR, "[class*='close'], [aria-label*='close'], [aria-label*='Close']")
            for btn in close_buttons[:2]:
                try:
                    btn.click()
                    time.sleep(0.5)
                except Exception:
                    pass
        except Exception:
            pass

        # Scroll to load more products
        scroll_to_bottom(driver, pause_time=2, max_scrolls=8)

        shoes = []
        seen_links = set()

        # Fleet Feet uses product-tile-link class for product links
        products = driver.find_elements(By.CSS_SELECTOR, "a.product-tile-link")
        print(f"Fleet Feet: found {len(products)} products with 'a.product-tile-link'")

        if not products:
            # Fallback: look for any product links
            print("Fleet Feet: trying link-based fallback")
            products = driver.find_elements(By.CSS_SELECTOR, "a[href*='/products/']")
            products = list({p.get_attribute("href"): p for p in products if p.get_attribute("href")}.values())[:50]

        for product in products:
            try:
                driver.execute_script("arguments[0].scrollIntoView();", product)

                # --- Product link ---
                link = None
                try:
                    if product.tag_name == "a":
                        link = product.get_attribute("href")
                    else:
                        link_el = product.find_element(By.CSS_SELECTOR, "a[href*='/products/'], a[href*='/shop/']")
                        link = link_el.get_attribute("href")
                except Exception:
                    try:
                        link_el = product.find_element(By.TAG_NAME, "a")
                        link = link_el.get_attribute("href")
                    except Exception:
                        continue

                if not link or link in seen_links:
                    continue
                seen_links.add(link)

                # --- Product name ---
                name = None
                for name_selector in [
                    "[class*='product-name']",
                    "[class*='ProductName']",
                    "[class*='title']",
                    "h2", "h3", "h4",
                    "[class*='name']",
                ]:
                    try:
                        name_el = product.find_element(By.CSS_SELECTOR, name_selector)
                        name = name_el.text.strip()
                        if name and len(name) > 3:
                            break
                    except Exception:
                        continue

                # Fallback: extract from alt text or aria-label
                if not name:
                    try:
                        img = product.find_element(By.TAG_NAME, "img")
                        name = img.get_attribute("alt") or ""
                    except Exception:
                        pass

                # Fallback: extract from URL (e.g., /products/mens-brooks-glycerin-23)
                if not name or len(name) < 3:
                    try:
                        url_parts = link.split("/products/")
                        if len(url_parts) > 1:
                            slug = url_parts[1].split("/")[0].split("?")[0]
                            # Remove gender prefix like "mens-" or "womens-"
                            slug = re.sub(r"^(mens|womens)-", "", slug)
                            name = slug.replace("-", " ").title()
                    except Exception:
                        pass

                if not name or len(name) < 3:
                    continue

                # --- Brand extraction ---
                brand = None
                for brand_selector in [
                    "[class*='brand']",
                    "[class*='Brand']",
                    "[data-brand]",
                ]:
                    try:
                        brand_el = product.find_element(By.CSS_SELECTOR, brand_selector)
                        brand = brand_el.text.strip() or brand_el.get_attribute("data-brand")
                        if brand:
                            break
                    except Exception:
                        continue

                # Extract brand from product name if not found
                if not brand:
                    known_brands = ["Nike", "Brooks", "HOKA", "Hoka", "Saucony", "ASICS", "Asics",
                                    "New Balance", "Adidas", "On", "Altra", "Mizuno", "Salomon"]
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
                    "[class*='price']",
                    "[class*='Price']",
                    "[data-price]",
                    "span[class*='sale']",
                    ".sale-price",
                    ".regular-price",
                ]:
                    try:
                        price_el = product.find_element(By.CSS_SELECTOR, price_selector)
                        raw = price_el.text.strip()
                        match = re.search(r"\$[\d,]+(?:\.\d{1,2})?", raw)
                        if match:
                            price = match.group(0)
                            break
                    except Exception:
                        continue

                if not price:
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
                    # Handle srcset for better quality
                    srcset = img_el.get_attribute("srcset")
                    if srcset:
                        img_url = srcset.split(",")[-1].strip().split(" ")[0]
                except Exception:
                    pass

                shoes.append({
                    "brand": brand,
                    "model": name,
                    "price": price,
                    "image": img_url,
                    "link": link if link.startswith("http") else f"https://www.fleetfeet.com{link}",
                    "retailer": "Fleet Feet"
                })

            except Exception as e:
                print(f"Fleet Feet: skipping product due to error: {e}")
                continue

        driver.quit()
        print(f"Fleet Feet: scraped {len(shoes)} shoes")
        return shoes

    except Exception as e:
        print(f"Fleet Feet scraper failed: {e}")
        driver.quit()
        return []


if __name__ == "__main__":
    results = scrape_fleetfeet()
    for shoe in results[:10]:
        print(shoe)
    print(f"Total: {len(results)} shoes")
