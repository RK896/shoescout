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


def scrape_roadrunnersports():
    """Scrape men's running shoes from Road Runner Sports (specialty running store)."""
    url = "https://www.roadrunnersports.com/category/mens/shoes/running"
    driver = get_chrome_driver()
    driver.set_page_load_timeout(30)

    try:
        driver.get(url)
        time.sleep(6)

        # Dismiss any cookie/popup banners
        try:
            WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'close') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'no thanks')]")
                )
            ).click()
            time.sleep(1)
        except Exception:
            pass

        # Try to close email signup modals
        try:
            close_buttons = driver.find_elements(By.CSS_SELECTOR, "[class*='close'], [aria-label*='close'], button[class*='modal-close']")
            for btn in close_buttons[:3]:
                try:
                    btn.click()
                    time.sleep(0.5)
                except Exception:
                    pass
        except Exception:
            pass

        # Scroll to load more products
        scroll_to_bottom(driver, pause_time=2, max_scrolls=6)

        shoes = []
        seen_links = set()

        # Road Runner Sports uses product links directly
        all_product_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/product/']")
        # Dedupe by href (removing query params for deduplication)
        seen_hrefs = {}
        for link in all_product_links:
            href = link.get_attribute("href")
            if href:
                base_href = href.split("?")[0]
                if base_href not in seen_hrefs:
                    seen_hrefs[base_href] = link
        products = list(seen_hrefs.values())
        print(f"Road Runner Sports: found {len(products)} unique products")

        for product in products:
            try:
                driver.execute_script("arguments[0].scrollIntoView();", product)

                # --- Product link ---
                link = None
                try:
                    if product.tag_name == "a":
                        link = product.get_attribute("href")
                    else:
                        link_el = product.find_element(By.CSS_SELECTOR, "a[href*='/product'], a[href*='/shoes']")
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

                # Get the parent container that has price info
                product_container = product
                try:
                    for _ in range(5):
                        parent = product_container.find_element(By.XPATH, "..")
                        if parent.find_elements(By.CSS_SELECTOR, "[class*='price']"):
                            product_container = parent
                            break
                        product_container = parent
                except Exception:
                    pass

                # --- Product name ---
                name = None
                for name_selector in [
                    "[class*='product-name']",
                    "[class*='ProductName']",
                    "[class*='tile-name']",
                    ".pdp-link",
                    "h2", "h3", "h4",
                    "[class*='name']",
                    ".link",
                ]:
                    try:
                        name_el = product.find_element(By.CSS_SELECTOR, name_selector)
                        name = name_el.text.strip()
                        if name and len(name) > 3:
                            break
                    except Exception:
                        continue

                # Fallback: extract from alt text
                if not name:
                    try:
                        img = product.find_element(By.TAG_NAME, "img")
                        name = img.get_attribute("alt") or ""
                    except Exception:
                        pass

                # Fallback: extract from URL (e.g., /product/48124/mens-brooks-ghost-17)
                if not name or len(name) < 3:
                    try:
                        url_parts = link.split("/product/")
                        if len(url_parts) > 1:
                            slug = url_parts[1].split("?")[0]
                            # Get the last segment (the product slug)
                            slug_parts = slug.split("/")
                            if len(slug_parts) > 1:
                                product_slug = slug_parts[-1]
                            else:
                                product_slug = slug_parts[0]
                            # Remove gender prefix like "mens-" or "womens-"
                            product_slug = re.sub(r"^(mens|womens)-", "", product_slug)
                            name = product_slug.replace("-", " ").title()
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
                    ".product-brand",
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
                                    "New Balance", "Adidas", "On", "Altra", "Mizuno", "Salomon",
                                    "Topo", "Merrell", "Karhu", "361", "Newton", "Diadora"]
                    for kb in known_brands:
                        if kb.lower() in name.lower():
                            brand = kb
                            break
                    if not brand:
                        parts = name.split()
                        brand = parts[0] if parts else "Unknown"

                # --- Price --- (use product_container which has price info)
                price = None
                for price_selector in [
                    "[class*='price-sales']",
                    "[class*='price-original']",
                    "[class*='price']",
                    "[class*='Price']",
                    "[data-price]",
                ]:
                    try:
                        price_el = product_container.find_element(By.CSS_SELECTOR, price_selector)
                        raw = price_el.text.strip()
                        match = re.search(r"\$[\d,]+(?:\.\d{1,2})?", raw)
                        if match:
                            price = match.group(0)
                            break
                    except Exception:
                        continue

                if not price:
                    try:
                        text = product_container.text
                        match = re.search(r"\$[\d,]+(?:\.\d{1,2})?", text)
                        if match:
                            price = match.group(0)
                    except Exception:
                        pass

                if not price:
                    price = "N/A"

                # --- Product image --- (use product_container for better image selection)
                img_url = None
                try:
                    img_el = product_container.find_element(By.TAG_NAME, "img")
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
                    "link": link if link.startswith("http") else f"https://www.roadrunnersports.com{link}",
                    "retailer": "Road Runner Sports"
                })

            except Exception as e:
                print(f"Road Runner Sports: skipping product due to error: {e}")
                continue

        driver.quit()
        print(f"Road Runner Sports: scraped {len(shoes)} shoes")
        return shoes

    except Exception as e:
        print(f"Road Runner Sports scraper failed: {e}")
        driver.quit()
        return []


if __name__ == "__main__":
    results = scrape_roadrunnersports()
    for shoe in results[:10]:
        print(shoe)
    print(f"Total: {len(results)} shoes")
