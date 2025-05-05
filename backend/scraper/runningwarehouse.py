import html, time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


def scrape_runningwarehouse():

    options = webdriver.ChromeOptions()
    options.add_argument("--disable-gpu") 
    options.add_argument("--no-sandbox")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/122.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.set_page_load_timeout(20)


    url = "https://www.runningwarehouse.com/Mens_Road_Running_Shoes/catpage-MBESTUSE.html"
    driver.get(url)
    time.sleep(3)
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'Accept All Cookies')]"))
        )
        accept_button = driver.find_element(By.XPATH, "//button[contains(text(), 'Accept All Cookies')]")
        accept_button.click()  # Accept the pop-up
        print("Pop-up accepted")
    except Exception as e:
        print("No pop-up or pop-up already accepted")
    WebDriverWait(driver, 10)


    products = driver.find_elements(By.CLASS_NAME, "cattable-wrap-cell")
    print(f"Found {len(products)} products")
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
                "brand": name.split()[0],
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

if __name__ == "__main__":
    results = scrape_runningwarehouse()
    print(len(results))
