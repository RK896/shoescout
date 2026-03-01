from driver_setup import get_chrome_driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import random


def scroll_to_bottom(driver, pause_time=4, max_scrolls=4):
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


def _extract_price(product):
    """Try multiple known Adidas price selectors, return first non-empty string found."""
    price_selectors = [
        (By.CLASS_NAME, "gl-price-item"),
        (By.CSS_SELECTOR, "[data-auto-id='gl-price-item']"),
        (By.CSS_SELECTOR, ".gl-price__value"),
        (By.CSS_SELECTOR, ".gl-price"),
        (By.CSS_SELECTOR, "span[class*='price']"),
    ]
    for by, selector in price_selectors:
        try:
            elements = product.find_elements(by, selector)
            for el in elements:
                text = el.text.strip()
                if text and "$" in text:
                    return text
        except Exception:
            continue
    return ""


def _extract_name(product):
    """Try multiple known Adidas name/title selectors."""
    name_selectors = [
        (By.CSS_SELECTOR, "[data-auto-id='product-card-description']"),
        (By.CLASS_NAME, "gl-product-card__name"),
        (By.CSS_SELECTOR, ".gl-product-card__details-main span"),
        (By.CSS_SELECTOR, "p[class*='name']"),
        (By.CSS_SELECTOR, "h3"),
        (By.CSS_SELECTOR, "span[class*='title']"),
    ]
    for by, selector in name_selectors:
        try:
            el = product.find_element(by, selector)
            text = el.text.strip()
            if text:
                return text
        except Exception:
            continue
    return ""


def scrape_adidas():
    url = "https://www.adidas.com/us/men-running-shoes"
    driver = get_chrome_driver()
    driver.set_page_load_timeout(30)

    try:
        driver.get(url)
    except Exception as e:
        print(f"Adidas page load error (may have timed out but content loaded): {e}")

    time.sleep(random.uniform(4, 7))

    # Handle cookie consent / privacy dialogs
    consent_xpaths = [
        "//button[contains(text(), 'Accept')]",
        "//button[contains(text(), 'Accept All')]",
        "//button[contains(text(), 'I Accept')]",
        "//button[@data-auto-id='glass-gdpr-default-consent-accept-button']",
    ]
    for xpath in consent_xpaths:
        try:
            btn = WebDriverWait(driver, 4).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            btn.click()
            time.sleep(1)
            break
        except Exception:
            continue

    # Wait for product cards to appear — try multiple known container selectors
    card_selectors = [
        "[data-auto-id='glass-product-card']",
        ".gl-product-card",
        "[data-testid='product-card']",
        "article[class*='product']",
        "li[class*='product']",
        "div[class*='product-card']",
    ]

    products = []
    used_selector = None
    for css in card_selectors:
        try:
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, css))
            )
            products = driver.find_elements(By.CSS_SELECTOR, css)
            if products:
                used_selector = css
                print(f"Adidas: found {len(products)} cards with selector '{css}'")
                break
        except Exception:
            continue

    if not products:
        print("Adidas: no product cards found on initial load — scrolling to trigger lazy load")

    scroll_to_bottom(driver)

    # Re-query after scrolling if needed
    if not products and used_selector:
        products = driver.find_elements(By.CSS_SELECTOR, used_selector)
    elif not products:
        for css in card_selectors:
            try:
                products = driver.find_elements(By.CSS_SELECTOR, css)
                if products:
                    used_selector = css
                    print(f"Adidas: found {len(products)} cards after scroll with selector '{css}'")
                    break
            except Exception:
                continue

    shoes = []
    seen_links = set()

    for product in products:
        try:
            # Scroll element into view to ensure dynamic content is rendered
            driver.execute_script("arguments[0].scrollIntoView();", product)

            name = _extract_name(product)
            price = _extract_price(product)

            # Product link
            link = ""
            try:
                anchor = product.find_element(By.TAG_NAME, "a")
                link = anchor.get_attribute("href") or ""
            except Exception:
                pass

            if not link or link in seen_links:
                continue
            seen_links.add(link)

            # Product image
            img_url = ""
            try:
                img = product.find_element(By.TAG_NAME, "img")
                img_url = (
                    img.get_attribute("src")
                    or img.get_attribute("data-src")
                    or img.get_attribute("data-lazy-src")
                    or ""
                )
            except Exception:
                pass

            if not name:
                name = "Adidas Running Shoe"

            shoes.append({
                "brand": "Adidas",
                "model": name,
                "price": price,
                "image": img_url,
                "link": link,
                "retailer": "Adidas",
            })
        except Exception:
            continue

    driver.quit()
    print(f"Adidas scraper finished: {len(shoes)} shoes collected")
    return shoes


if __name__ == "__main__":
    results = scrape_adidas()
    for shoe in results:
        print(shoe)
    print(f"Total: {len(results)}")
