from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def asics_scraper():
    url = "https://www.asics.com/us/en-us/mens-running-shoes/c/aa10201000/?start=0&sz=350"
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--disable-gpu") 
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")  
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64" +
                                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    driver.set_page_load_timeout(30)
    driver.get(url)
    
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'OK')]"))
        )
        accept_button = driver.find_element(By.XPATH, "//button[contains(text(), 'OK')]")
        accept_button.click()  # Accept the pop-up
        print("Pop-up accepted")
    except Exception as e:
        print("No pop-up or pop-up already accepted")
    WebDriverWait(driver, 10)
    

    products = driver.find_elements(By.CLASS_NAME, "grid-tile")
    
    shoes = []

    for shoe in products:
        
        name_tag = shoe.find_element(By.CSS_SELECTOR, ".product-tile__text.product-tile__text--large")
        price_tag = shoe.find_element(By.CLASS_NAME, "price-sales")
        link_tag = driver.find_elements(By.CLASS_NAME, "product-tile__link")

        try:
            name = name_tag.text.strip()
            price = price_tag.text.strip()
            link = link_tag.get_attribute("href")

            shoes.append({
                "model": name,
                "price": price,
                "link": link,
                "brand": name.split()[0],
                "retailer": "Asics"
            })
        except Exception as e:
            print(f"Skipping product due to missing info {e}")

    driver.quit()
    return shoes


if __name__ == "__main__":
    count = 0
    shoes = asics_scraper()
    for shoe in shoes:
        print(shoe)
        count +=1 
    print(count)
