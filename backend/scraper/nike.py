
from selenium import webdriver
from selenium.webdriver.chrome import options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import time

#automating scrolling to load content
def scroll_to_bottom(driver, pause_time=5, max_scrolls=3):
    last_height = driver.execute_script("return document.body.scrollHeight")
    scrolls = 0

    while scrolls < max_scrolls:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause_time)  #wait for content to load
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break  #if theres no new content
        last_height = new_height
        scrolls += 1

def scrape_nike():
    url = "https://www.nike.com/w/mens-running-shoes-37v7jznik1zy7ok"
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--disable-gpu") 
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")  
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--headless")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.set_page_load_timeout(10)
    driver.get(url)

    scroll_to_bottom(driver)

    shoes = []
    product_cards = driver.find_elements(By.CLASS_NAME, "product-card")
    for product in product_cards:

        try:
            name_tag = product.find_element(By.CLASS_NAME, "product-card__title")
            price_tag = product.find_element(By.CLASS_NAME, "product-price")
            img_tag = product.find_element(By.CLASS_NAME, "product-card__hero-image")
            img_url = img_tag.get_attribute("src") if img_tag else None
            link_tag = product.find_element(By.CLASS_NAME, "product-card__img-link-overlay")

    
            shoes.append({
                "brand": "Nike",
                "model": name_tag.text.strip(),
                "price": price_tag.text.strip(),
                "link": link_tag.get_attribute("href"),
                "image": img_url,
                "retailer": "Nike"
                })
        except Exception as e:
            print(f"skipping a product due to missing info")
    
    driver.quit()
    return shoes

if __name__ == "__main__": 
    results = scrape_nike()
    print(len(results))
        

