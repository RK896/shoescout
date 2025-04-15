import requests
from bs4 import BeautifulSoup

def scrape_runningwarehouse():

    url = "https://www.runningwarehouse.com/Mens_Road_Running_Shoes/catpage-MBESTUSE.html"
    header = {
        'User-Agent': 'Mozilla/5.0'
    }

    r = requests.get(url, headers=header)

    soup = BeautifulSoup(r.text, "html.parser")

    shoes = []

    for product in soup.find_all("div", class_="cattable-wrap-cell"): 
        name_tag = product.find("div", class_="cattable-wrap-cell-info-name")
        price_tag = product.find("div", class_="cattable-wrap-cell-info-price")
        link_tag = product.find("a", class_="cattable-wrap-cell-info")

        if name_tag and price_tag and link_tag:
            name = name_tag.text.strip()
            raw_price = price_tag.text.strip()
            if raw_price.count("$") > 1:
                prices = raw_price.split("$")
                price = "$" + prices[1]
                original_price = "$" + prices[2]
            else:
                price = raw_price
                original_price = raw_price
            link = link_tag["href"]

            shoes.append({
                "model": name,
                "price": price,
                "original price": original_price,
                "link": link,
                "brand": name.split()[0],
                "retailer": "Running Warehouse"
            })
    return shoes

if __name__ == "__main__":
    results = scrape_runningwarehouse()
    count = 0
    for shoe in results:
        print(shoe)
        count +=1 

    print(count)
