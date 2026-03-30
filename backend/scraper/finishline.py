"""
Finish Line Selenium-based scraper.

Finish Line (owned by JD Sports) has strong bot protection that blocks
direct HTTP requests. This scraper uses Selenium to render the page
and extract product data.

The scraper navigates to running shoe category pages and extracts
product information from the rendered HTML.
"""
import re
import time
from typing import Optional

from driver_setup import get_chrome_driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# Known running shoe brands
KNOWN_BRANDS = {
    "nike": "Nike",
    "brooks": "Brooks",
    "hoka": "HOKA",
    "saucony": "Saucony",
    "asics": "ASICS",
    "new balance": "New Balance",
    "adidas": "adidas",
    "on": "On",
    "mizuno": "Mizuno",
    "altra": "Altra",
    "jordan": "Jordan",
    "under armour": "Under Armour",
    "reebok": "Reebok",
    "puma": "PUMA",
}


def _scroll_to_bottom(driver, pause_time: float = 2.0, max_scrolls: int = 10):
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


def _dismiss_popups(driver):
    """Dismiss any cookie banners or popup modals."""
    popup_selectors = [
        "button[class*='close']",
        "button[aria-label*='close']",
        "button[aria-label*='Close']",
        "[class*='modal-close']",
        "[class*='popup-close']",
        "button[class*='dismiss']",
        "#onetrust-accept-btn-handler",  # Cookie consent
    ]

    for selector in popup_selectors:
        try:
            buttons = driver.find_elements(By.CSS_SELECTOR, selector)
            for btn in buttons[:3]:
                try:
                    btn.click()
                    time.sleep(0.5)
                except Exception:
                    pass
        except Exception:
            pass


def _is_kids_shoe(name: str) -> bool:
    """Check if a product is a kids shoe."""
    name_lower = name.lower()
    kids_indicators = [
        "little kid", "big kid", "toddler", "infant", "kids'", "kids",
        "youth", "grade school", "preschool", "(ps)", "(gs)", "(td)",
        "child", "boys'", "girls'"
    ]
    return any(indicator in name_lower for indicator in kids_indicators)


def _extract_brand(name: str) -> Optional[str]:
    """Extract brand from product name."""
    name_lower = name.lower()

    for brand_key, brand_name in KNOWN_BRANDS.items():
        if brand_key in name_lower:
            return brand_name
    return None


def _clean_model_name(name: str, brand: str) -> str:
    """Clean up the product name to get a standardized model name."""
    model = name.strip()

    # Remove gender indicators
    model = re.sub(r"\b(Men's|Women's|Mens|Womens|Men|Women)\b", "", model, flags=re.IGNORECASE)

    # Remove "Running Shoe(s)" suffix
    model = re.sub(r"\s+Running\s+Shoes?$", "", model, flags=re.IGNORECASE)

    # Clean up extra whitespace
    model = " ".join(model.split())

    # Ensure brand prefix is present
    if brand and not model.lower().startswith(brand.lower()):
        model = f"{brand} {model}"

    return model.strip()


def scrape_finishline() -> list[dict]:
    """
    Scrape running shoes from Finish Line.

    Uses Selenium to navigate category pages and extract product data.

    Returns:
        List of shoe dicts compatible with existing add_shoes_to_db().
    """
    # Category URLs for running shoes
    urls = [
        "https://www.finishline.com/store/men/shoes/running/_/N-30s3rsZ1z141t7Z33zqf",
        "https://www.finishline.com/store/women/shoes/running/_/N-30s3rsZ1z141tkZ33zqf",
    ]

    driver = get_chrome_driver()
    driver.set_page_load_timeout(45)

    all_shoes = []
    seen_links = set()

    try:
        for url in urls:
            print(f"Finish Line: Scraping {url[:60]}...")

            try:
                driver.get(url)
                time.sleep(5)
            except Exception as e:
                print(f"Finish Line: Error loading page: {e}")
                continue

            # Dismiss any popups
            _dismiss_popups(driver)

            # Scroll to load more products
            _scroll_to_bottom(driver, pause_time=2.0, max_scrolls=8)

            # Find product cards
            product_selectors = [
                "[class*='product-card']",
                "[class*='productCard']",
                "[class*='product-tile']",
                "[data-productid]",
                ".product-container",
                "article[class*='product']",
            ]

            products = []
            for selector in product_selectors:
                products = driver.find_elements(By.CSS_SELECTOR, selector)
                if products:
                    print(f"Finish Line: Found {len(products)} products with selector: {selector}")
                    break

            if not products:
                # Fallback: find all product links
                product_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/product/']")
                # Dedupe by href
                seen_hrefs = {}
                for link in product_links:
                    href = link.get_attribute("href")
                    if href:
                        base_href = href.split("?")[0]
                        if base_href not in seen_hrefs:
                            seen_hrefs[base_href] = link
                products = list(seen_hrefs.values())
                print(f"Finish Line: Found {len(products)} products via links")

            for product in products:
                try:
                    # Scroll into view
                    driver.execute_script("arguments[0].scrollIntoView();", product)

                    # Get product link
                    link = None
                    try:
                        if product.tag_name == "a":
                            link = product.get_attribute("href")
                        else:
                            link_el = product.find_element(By.CSS_SELECTOR, "a[href*='/product']")
                            link = link_el.get_attribute("href")
                    except Exception:
                        try:
                            link_el = product.find_element(By.TAG_NAME, "a")
                            link = link_el.get_attribute("href")
                        except Exception:
                            continue

                    if not link or link in seen_links:
                        continue

                    base_link = link.split("?")[0]
                    if base_link in seen_links:
                        continue
                    seen_links.add(base_link)

                    # Get product name
                    name = None
                    name_selectors = [
                        "[class*='product-name']",
                        "[class*='productName']",
                        "[class*='title']",
                        "h2", "h3", "h4",
                        "[class*='name']",
                    ]

                    for selector in name_selectors:
                        try:
                            name_el = product.find_element(By.CSS_SELECTOR, selector)
                            name = name_el.text.strip()
                            if name and len(name) > 3:
                                break
                        except Exception:
                            continue

                    # Fallback: image alt text
                    if not name:
                        try:
                            img = product.find_element(By.TAG_NAME, "img")
                            name = img.get_attribute("alt") or ""
                        except Exception:
                            pass

                    if not name or len(name) < 3:
                        continue

                    # Skip kids shoes
                    if _is_kids_shoe(name):
                        continue

                    # Extract brand
                    brand = _extract_brand(name)
                    if not brand:
                        continue

                    # Get price
                    price = None
                    price_selectors = [
                        "[class*='sale-price']",
                        "[class*='salePrice']",
                        "[class*='price-sale']",
                        "[class*='price']",
                        "[class*='Price']",
                    ]

                    for selector in price_selectors:
                        try:
                            price_el = product.find_element(By.CSS_SELECTOR, selector)
                            price_text = price_el.text.strip()
                            match = re.search(r"\$[\d,]+(?:\.\d{2})?", price_text)
                            if match:
                                price = match.group(0)
                                break
                        except Exception:
                            continue

                    if not price:
                        try:
                            text = product.text
                            match = re.search(r"\$[\d,]+(?:\.\d{2})?", text)
                            if match:
                                price = match.group(0)
                        except Exception:
                            pass

                    if not price:
                        price = "N/A"

                    # Get image
                    img_url = None
                    try:
                        img_el = product.find_element(By.TAG_NAME, "img")
                        img_url = img_el.get_attribute("src") or img_el.get_attribute("data-src")
                        # Handle srcset
                        srcset = img_el.get_attribute("srcset")
                        if srcset:
                            img_url = srcset.split(",")[-1].strip().split(" ")[0]
                    except Exception:
                        pass

                    # Clean model name
                    model = _clean_model_name(name, brand)

                    # Ensure full URL
                    if link and not link.startswith("http"):
                        link = f"https://www.finishline.com{link}"

                    all_shoes.append({
                        "brand": brand,
                        "model": model,
                        "price": price,
                        "image": img_url,
                        "link": link,
                        "retailer": "Finish Line"
                    })

                except Exception as e:
                    print(f"Finish Line: Error parsing product: {e}")
                    continue

            print(f"Finish Line: Scraped {len(all_shoes)} shoes so far")
            time.sleep(2)

    except Exception as e:
        print(f"Finish Line scraper failed: {e}")
    finally:
        driver.quit()

    # Deduplicate by model name, keeping lowest price
    unique_shoes: dict[str, dict] = {}
    for shoe in all_shoes:
        key = shoe["model"].lower()
        if key not in unique_shoes:
            unique_shoes[key] = shoe
        else:
            try:
                existing_price = float(unique_shoes[key]["price"].replace("$", "").replace(",", ""))
                new_price = float(shoe["price"].replace("$", "").replace(",", ""))
                if new_price < existing_price:
                    unique_shoes[key] = shoe
            except (ValueError, AttributeError):
                pass

    result = list(unique_shoes.values())
    print(f"Finish Line: Scraped {len(result)} unique shoes")
    return result


if __name__ == "__main__":
    shoes = scrape_finishline()
    print(f"\nTotal: {len(shoes)} shoes")
    for shoe in shoes[:10]:
        print(f"  {shoe['brand']} - {shoe['model']}: {shoe['price']}")
