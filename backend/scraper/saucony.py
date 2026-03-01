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


def scrape_saucony():
    # Primary URL for men's running shoes; fallback uses gender refinement param
    url = "https://www.saucony.com/en/mens-running-shoes/"

    driver = get_chrome_driver()
    driver.set_page_load_timeout(30)
    driver.get(url)

    # Wait for product tiles to appear after JS renders the page
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CLASS_NAME, "product-tile"))
        )
    except Exception:
        # Tiles may not have loaded; scroll anyway and attempt scraping
        pass

    # Dismiss cookie/consent banner if present
    try:
        consent_btn = driver.find_element(
            By.XPATH,
            "//button[contains(translate(text(),'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'ACCEPT') "
            "or contains(translate(text(),'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'AGREE') "
            "or contains(translate(text(),'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'OK')]"
        )
        consent_btn.click()
        time.sleep(1)
    except Exception:
        pass

    # Scroll to trigger lazy-loaded product tiles
    scroll_to_bottom(driver, pause_time=3, max_scrolls=5)

    shoes = []
    seen_links = set()

    # Saucony runs on SFCC; product tiles use the standard "product-tile" class.
    # Within each tile:
    #   - Name/link: .pdp-link a  (SFCC standard)
    #   - Price:     .price .value  or  .price  (SFCC standard)
    #   - Image:     .tile-image img  or  img[class*="tile-image"]
    products = driver.find_elements(By.CLASS_NAME, "product-tile")

    for product in products:
        try:
            # --- Product name and link ---
            # SFCC standard: anchor inside .pdp-link carries both the name and href
            try:
                name_el = product.find_element(By.CSS_SELECTOR, ".pdp-link a")
                name = name_el.text.strip()
                link = name_el.get_attribute("href") or ""
            except Exception:
                # Fallback: first anchor in the tile
                name_el = product.find_element(By.TAG_NAME, "a")
                name = name_el.text.strip()
                link = name_el.get_attribute("href") or ""

            if not name:
                # Try aria-label or title attribute as last resort
                name = name_el.get_attribute("aria-label") or name_el.get_attribute("title") or ""

            # Skip duplicate links (colour-swatch duplicates share the same tile area)
            if link and link in seen_links:
                continue
            if link:
                seen_links.add(link)

            # --- Price ---
            # SFCC renders sale/regular prices inside .price; prefer .value span when present
            try:
                price_el = product.find_element(By.CSS_SELECTOR, ".price .value")
                price = price_el.get_attribute("content") or price_el.text.strip()
                if price and not price.startswith("$"):
                    price = f"${price}"
            except Exception:
                try:
                    price_el = product.find_element(By.CLASS_NAME, "price")
                    price = price_el.text.strip()
                except Exception:
                    price = ""

            # --- Image ---
            # SFCC tiles use .tile-image on the <img> tag itself
            try:
                img_el = product.find_element(By.CSS_SELECTOR, ".tile-image")
                img = (
                    img_el.get_attribute("src")
                    or img_el.get_attribute("data-src")
                    or ""
                )
            except Exception:
                try:
                    img_el = product.find_element(By.TAG_NAME, "img")
                    img = (
                        img_el.get_attribute("src")
                        or img_el.get_attribute("data-src")
                        or ""
                    )
                except Exception:
                    img = ""

            # Skip tiles that yielded no useful data
            if not name and not link:
                continue

            shoes.append({
                "brand": "Saucony",
                "model": name,
                "price": price,
                "image": img,
                "link": link,
                "retailer": "Saucony",
            })

        except Exception:
            continue

    driver.quit()
    return shoes


if __name__ == "__main__":
    results = scrape_saucony()
    for shoe in results:
        print(shoe)
    print(f"Total: {len(results)}")
