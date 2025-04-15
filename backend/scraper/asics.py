import requests
from bs4 import BeautifulSoup

def asics_scraper():
    url = "https://www.asics.com/us/en-us/mens-running-shoes/c/aa10201000/?start=0&sz=50"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")

    shoes = []

    for shoe in soup.findAll("li", class_="product-tile"):
        name_tag = shoe.find("div", class_= "product-tile__text")
        price_tag = shoe.find("span", class_="price-sales")
        link_tag = shoe.find("a", class_="product-tile__link")

        if name_tag and price_tag and link_tag:
            name = name_tag.text.strip()
            price = price_tag.text.strip()
            link = link_tag["href"]

            shoes.append({
                "model": name,
                "price": price,
                "link": link,
                "brand": name.split()[0],
                "retailer": "Asics"
            })
    return shoes


if __name__ == "__main__":
    count = 0
    shoes = asics_scraper()
    for shoe in shoes:
        print(shoe)
        count +=1 
    print(count)
