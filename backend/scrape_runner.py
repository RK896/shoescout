"""
Standalone scraper runner used by GitHub Actions (scraper.yaml).
Imports scrapers directly and writes to MongoDB without starting the FastAPI app.
"""
import os
import re
import importlib
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv

load_dotenv()


def parse_price(price_str: str) -> float:
    if not price_str:
        return float('inf')
    cleaned = price_str.replace(',', '')
    match = re.search(r'[\d]+\.?\d*', cleaned)
    return float(match.group()) if match else float('inf')


def add_shoes_to_db(shoes, collection):
    for shoe in shoes:
        shoe_model = shoe.get("model", "")
        if not shoe_model or not shoe_model.strip():
            continue
        brand = shoe.get("brand", "")
        price = shoe.get("price", "")
        image = shoe.get("image")
        retailer = shoe.get("retailer", "")
        link = shoe.get("link", "")

        existing_shoe = collection.find_one({"model": shoe_model})
        if existing_shoe:
            existing_retailer = None
            for retailer_entry in existing_shoe.get("retailers", []):
                if retailer_entry["retailer"] == retailer:
                    existing_retailer = retailer_entry
                    break

            if existing_retailer:
                existing_price_val = parse_price(existing_retailer.get("price", ""))
                new_price_val = parse_price(price)
                if new_price_val < existing_price_val:
                    collection.update_one(
                        {"model": shoe_model, "retailers.retailer": retailer},
                        {"$set": {"retailers.$.price": price}}
                    )
            else:
                collection.update_one(
                    {"model": shoe_model},
                    {"$addToSet": {"retailers": {"retailer": retailer, "price": price, "link": link}}}
                )
        else:
            collection.update_one(
                {"model": shoe_model},
                {
                    "$set": {"brand": brand, "model": shoe_model, "image": image},
                    "$addToSet": {"retailers": {"retailer": retailer, "price": price, "link": link}}
                },
                upsert=True
            )


def run_all_scrapers():
    uri = os.getenv("MONGO_URI")
    client = MongoClient(uri, server_api=ServerApi('1'))
    db = client["shoe_scout"]
    collection = db["shoes"]

    all_shoes = []

    scrapers = [
        ("Running Warehouse", "scraper.runningwarehouse", "scrape_runningwarehouse"),
        ("Nike", "scraper.nike", "scrape_nike"),
        ("New Balance", "scraper.newbalance", "scrape_newbalance"),
        ("Brooks", "scraper.brooks", "scrape_brooks"),
        ("HOKA", "scraper.hoka", "scrape_hoka"),
        ("Saucony", "scraper.saucony", "scrape_saucony"),
        ("Adidas", "scraper.adidas", "scrape_adidas"),
        ("Zappos", "scraper.zappos", "scrape_zappos"),
        ("Fleet Feet", "scraper.fleetfeet", "scrape_fleetfeet"),
        ("Road Runner Sports", "scraper.roadrunnersports", "scrape_roadrunnersports"),
    ]

    for name, module_path, func_name in scrapers:
        try:
            module = importlib.import_module(module_path)
            func = getattr(module, func_name)
            shoes = func()
            print(f"{name}: scraped {len(shoes)} shoes")
            all_shoes.extend(shoes)
        except Exception as e:
            print(f"{name} scraper failed: {e}")

    add_shoes_to_db(all_shoes, collection)
    print(f"\nTotal scraped: {len(all_shoes)} shoes stored/updated in MongoDB")
    return len(all_shoes)


if __name__ == "__main__":
    run_all_scrapers()
