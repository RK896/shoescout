import html, time
from driver_setup import get_chrome_driver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

# Map first-word of shoe name to correct brand name for multi-word brands
_BRAND_MAP = {
    "new": "New Balance",
    "on": "On Running",
    "la": "La Sportiva",
    "k-swiss": "K-Swiss",
}

def _extract_brand(name: str) -> str:
    first = name.split()[0].lower() if name.split() else ""
    return _BRAND_MAP.get(first, name.split()[0] if name.split() else "Unknown")


def scrape_runningwarehouse():
    url = "https://www.runningwarehouse.com/Mens_Road_Running_Shoes/catpage-MBESTUSE.html"
    driver = get_chrome_driver()
    driver.get(url)
    time.sleep(3)
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'Accept All Cookies')]"))
        )
        accept_button = driver.find_element(By.XPATH, "//button[contains(text(), 'Accept All Cookies')]")
        accept_button.click()  
    except Exception as e:
        time.sleep(2)
    WebDriverWait(driver, 10)


    products = driver.find_elements(By.CLASS_NAME, "cattable-wrap-cell")
    shoes = []
    seen = set()

    for product in products: 

        try:
            name_tag = product.find_element(By.CLASS_NAME, "cattable-wrap-cell-info-name")
            price_tag = product.find_element(By.CLASS_NAME, "cattable-wrap-cell-info-price")
            link_tag = product.find_element(By.CLASS_NAME, "cattable-wrap-cell-info")
            driver.execute_script("arguments[0].scrollIntoView();", product)
            image_tag = product.find_element(By.CLASS_NAME, "cattable-wrap-cell-imgwrap-inner-img")
            img_url = html.unescape(image_tag.get_attribute("src")) if image_tag else None

            name = name_tag.text.strip()
            raw_price = price_tag.text.strip()
            link = link_tag.get_attribute("href")
            img_srcset = image_tag.get_attribute("srcset")
            img_url = html.unescape(img_srcset.split(",")[0].split()[0]) if img_srcset else image_tag.get_attribute("src")

            if link in seen:
                continue
            seen.add(link)
            
            if raw_price.count("$") > 1:
                prices = raw_price.split("$")
                price = "$" + prices[1]
            else:
                price = raw_price

            shoes.append({
                "brand": _extract_brand(name),
                "model": name,
                "price": price,
                "image": img_url,
                "link": link,
                "retailer": "Running Warehouse"
            })
        except Exception as e:
            print(f"skipping product due to missing info",{e})
            continue
    driver.quit()

    return shoes


