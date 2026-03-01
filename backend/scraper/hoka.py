from driver_setup import get_chrome_driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time


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


def scrape_hoka():
    url = "https://www.hoka.com/en/us/mens-road-running-shoes/"
    driver = get_chrome_driver()
    driver.set_page_load_timeout(30)
    driver.get(url)

    # Wait for product tiles to be present in the DOM
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CLASS_NAME, "product-tile"))
        )
    except Exception:
        # If the standard class isn't found immediately, give JS more time
        time.sleep(8)

    # Dismiss any cookie/popup banners if present
    try:
        cookie_btn = driver.find_element(
            By.XPATH,
            "//button[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]"
        )
        cookie_btn.click()
        time.sleep(1)
    except Exception:
        pass

    # Scroll to trigger lazy-loaded images and infinite scroll / load-more
    scroll_to_bottom(driver, pause_time=3, max_scrolls=5)

    shoes = []
    seen_links = set()

    # HOKA on SFRA uses standard product-tile class as the tile wrapper
    products = driver.find_elements(By.CLASS_NAME, "product-tile")

    for product in products:
        try:
            # --- Product name ---
            # SFRA standard: <a class="link" href="..."> inside a <div class="pdp-link">
            # HOKA may use "product-tile__name" or "pdp-link" depending on their cartridge version
            name = None
            for name_selector in ["pdp-link", "product-tile__name", "product-name", "link"]:
                try:
                    name_el = product.find_element(By.CLASS_NAME, name_selector)
                    name = name_el.text.strip()
                    if name:
                        break
                except Exception:
                    continue

            if not name:
                continue

            # --- Product link ---
            # Primary: anchor inside pdp-link; fallback: first anchor in tile
            link = None
            for link_selector in [
                "a.link",
                ".pdp-link a",
                ".product-tile__name a",
                "a[href*='/en/us/']",
            ]:
                try:
                    link_el = product.find_element(By.CSS_SELECTOR, link_selector)
                    link = link_el.get_attribute("href")
                    if link:
                        break
                except Exception:
                    continue

            if not link:
                try:
                    link = product.find_element(By.TAG_NAME, "a").get_attribute("href")
                except Exception:
                    link = None

            # Deduplicate by link
            if link and link in seen_links:
                continue
            if link:
                seen_links.add(link)

            # --- Price ---
            # SFRA standard: <div class="price"> containing <span class="value">
            # HOKA may also use "product-tile__price" or "sales"
            price = None
            for price_selector in [
                "price",
                "product-tile__price",
                "sales",
                "pricing",
            ]:
                try:
                    price_el = product.find_element(By.CLASS_NAME, price_selector)
                    price = price_el.text.strip()
                    if price:
                        break
                except Exception:
                    continue

            # --- Product image ---
            # SFRA standard: <div class="tile-image"> or <img> directly inside tile
            img = None
            for img_selector in [
                "tile-image",
                "product-tile__image",
                "product-image",
            ]:
                try:
                    img_el = product.find_element(By.CLASS_NAME, img_selector)
                    # Try srcset first for best-quality URL, then src
                    srcset = img_el.get_attribute("srcset")
                    if srcset:
                        img = srcset.split(",")[-1].strip().split(" ")[0]
                    else:
                        img = img_el.get_attribute("src")
                    if img:
                        break
                except Exception:
                    continue

            if not img:
                try:
                    img_el = product.find_element(By.TAG_NAME, "img")
                    srcset = img_el.get_attribute("srcset")
                    if srcset:
                        img = srcset.split(",")[-1].strip().split(" ")[0]
                    else:
                        img = img_el.get_attribute("src")
                except Exception:
                    img = None

            shoes.append({
                "brand": "HOKA",
                "model": name,
                "price": price if price else "",
                "image": img,
                "link": link,
                "retailer": "HOKA"
            })

        except Exception:
            continue

    driver.quit()
    return shoes


if __name__ == "__main__":
    results = scrape_hoka()
    for shoe in results:
        print(shoe)
    print(f"Total: {len(results)} shoes")
