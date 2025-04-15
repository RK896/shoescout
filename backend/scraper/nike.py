
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.microsoft import EdgeChromiumDriverManager
import time

#automating scrolling to load content
def scroll_to_bottom(driver, pause_time=40, max_scrolls=20):
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
    edge_options = Options()
    edge_options.add_argument("--disable-gpu") 
    edge_options.add_argument("--blink-settings=imagesEnabled=false")  
    edge_options.add_argument("--no-sandbox")
    edge_options.add_argument("--headless")
    driver = webdriver.Edge(service=Service(EdgeChromiumDriverManager().install()), options=edge_options)
    driver.set_page_load_timeout(300)
    driver.get(url)
    time.sleep(3)

    scroll_to_bottom(driver)

    shoes = []
    product_cards = driver.find_elements(By.CLASS_NAME, "product-card")
    for product in product_cards:
        name_tag = product.find_element(By.CLASS_NAME, "product-card__title")
        price_tag = product.find_element(By.CLASS_NAME, "product-price")
        link_tag = product.find_element(By.CLASS_NAME, "product-card__img-link-overlay")

        if name_tag and price_tag and link_tag: 
            shoes.append({
                "name": name_tag.text.strip(),
                "price": price_tag.text.strip(),
                "url": link_tag.get_attribute("href"),
                "brand": "Nike"
                })
    driver.quit()
    return shoes

if __name__ == "__main__": 
    results = scrape_nike()
    count = 0
    for shoe in results: 
        print(shoe)
        count+=1
    print(count)
        

