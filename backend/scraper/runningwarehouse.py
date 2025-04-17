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
        image_tag = product.find("div", class_="cattable-wrap-cell-imgwrap")
        img_url = None
        if image_tag:
            image_link_tag = image_tag.find("a", class_="cattable-wrap-cell-imgwrap-inner")
            if image_link_tag:
                img = image_link_tag.find("img")
                if img and img.has_attr("src"):
                    img_url = img["src"]

                    # Ensure that the image is the main product image, not an ad or other content.
                    if "watermark" in img_url:
                        img_url = img_url.split("?")[0]  # Remove query parameters (like nw=500, etc.)


        if name_tag and price_tag and link_tag and image_tag:
            name = name_tag.text.strip()
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
