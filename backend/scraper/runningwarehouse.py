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
        image_tag = product.find("img", class_="cattable-wrap-cell-imgwrap-inner-img")
            


        if name_tag and price_tag and link_tag and image_tag:
            name = name_tag.text.strip()
            img_url = image_tag["src"]
            raw_price = price_tag.text.strip()
            if raw_price.count("$") > 1:
                prices = raw_price.split("$")
                price = "$" + prices[1]
            else:
                price = raw_price

            link = link_tag["href"]

            shoes.append({
                "brand": name.split()[0],
                "model": name,
                "price": price,
                "image": img_url,
                "link": link,
                "retailer": "Running Warehouse"
            })
    return shoes

if __name__ == "__main__":
    results = scrape_runningwarehouse()
