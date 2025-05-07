from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import time


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
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--disable-gpu") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/122.0.0.0 Safari/537.36")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")


    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.set_page_load_timeout(10)
    driver.get(url)
    

    scroll_to_bottom(driver)
    shoes = []
    product_cards = driver.find_elements(By.CLASS_NAME, "product-tile")
    for product in product_cards:

        try:
            name_tag = product.find_element(By.CLASS_NAME, "link")
            price_tag = product.find_element(By.CLASS_NAME, "sales")
            link_tag = product.find_element(By.CSS_SELECTOR, ".image-container a")

            img_tag = product.find_element(By.CSS_SELECTOR, 'source[type="image/jpeg"]')
            srcset = img_tag.get_attribute("srcset") if img_tag else None

            if srcset:
                urls = [u.strip().split(" ")[0] for u in srcset.split(",")]
                img_url = urls[-1] if urls else None

            print("High-res Image URL:", img_url)

    
            shoes.append({
                "brand": "New Balance",
                "model": name_tag.text.strip(),
                "price": price_tag.text.strip(),
                "link": "https://www.newbalance.com" + link_tag.get_attribute("href"),
                "image": img_url,
                "retailer": "New Balance"
                })
        except Exception as e:
            print(f"skipping a product due to missing info")
            continue
    
    driver.quit()
    return shoes

if __name__ == "__main__": 
    results = scrape_newbalance()
    print(len(results))
        



