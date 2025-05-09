from driver_setup import get_chrome_driver
from selenium.webdriver.common.by import By
import time, random


def scroll_to_bottom(driver, pause_time=5, max_scrolls=3):
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

def scrape_newbalance():
    url = "https://www.newbalance.com/men/shoes/running/"

    driver = get_chrome_driver()
    driver.set_page_load_timeout(10)
    driver.get(url)
    time.sleep(random.uniform(2, 5))

    scroll_to_bottom(driver)
    shoes = []
    product_cards = driver.find_elements(By.CLASS_NAME, "product-tile")
    for product in product_cards:

        try:
            name_tag = product.find_element(By.CLASS_NAME, "link")
            price_tag = product.find_element(By.CLASS_NAME, "sales")
            link_tag = product.find_element(By.CSS_SELECTOR, ".image-container a")
            driver.execute_script("arguments[0].scrollIntoView();", product)
            img_tag = product.find_element(By.CSS_SELECTOR, 'source[type="image/jpeg"]')
            srcset = img_tag.get_attribute("srcset") if img_tag else None

            if srcset:
                urls = [u.strip().split(" ")[0] for u in srcset.split(",")]
                img_url = urls[-1] if urls else None
    
            shoes.append({
                "brand": "New Balance",
                "model": "New Balance " + name_tag.text.strip(),
                "price": price_tag.text.strip(),
                "link": "https://www.newbalance.com" + link_tag.get_attribute("href"),
                "image": img_url,
                "retailer": "New Balance"
                })
        except Exception as e:
            continue
    
    driver.quit()
    return shoes
