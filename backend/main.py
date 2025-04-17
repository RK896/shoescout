from pymongo import MongoClient
from pymongo.server_api import ServerApi
from scraper import nike, runningwarehouse, asics

def get_db(): 
    uri = "mongodb+srv://shoeScout:4kN0XfmvxGpXvKBY@shoescout.lenwqmf.mongodb.net/?retryWrites=true&w=majority&appName=shoeScout"
    client = MongoClient(uri, server_api=ServerApi('1'))
    try:
        client.admin.command('ping')
        print("Pinged your deployment. You successfully connected to MongoDB!")
    except Exception as e:
        print(e)
    
    db = client["shoe_scout"]
    return db

def add_shoes_to_db(shoes, db):
    collection = db["shoes"]

    for shoe in shoes: 
        model = shoe["model"]
        brand = shoe["brand"]
        price = shoe["price"]
        image = shoe["image"]
        retailer = shoe["retailer"]
        link = shoe["link"]

        existing_shoe = collection.find_one({"model": model})
        if existing_shoe:
            existing_retailer = None
            for retailer_entry in existing_shoe["retailers"]:
                existing_retailer = retailer_entry
                break

            if existing_retailer:
                existing_price = float(existing_retailer["price"].replace("$", ""))
                new_price = float(price.replace("$", ""))

                if new_price < existing_price:
                    collection.update_one({"model": model, "retailers.retailer": retailer}, 
                                          {"$set": {
                                              "retailer.$.price": price
                                          }})
            else:
                collection.update_one({"model:": model}, 
                {
                    "$addToSet": {
                        "retailers": {
                            "retailer": retailer,
                            "price": price,
                            "link": link
                        }
                    } 
                })


        else:
            collection.update_one(
                {"model": shoe["model"]},
                {
                    "$set": {
                        "brand": shoe["brand"],
                        "model": shoe["model"],
                        "image": shoe["image"]
                    },
                    "$addToSet": {
                        "retailers": {
                            "retailer": shoe["retailer"],
                            "price": shoe["price"],
                            "link": shoe["link"]
                        }
                    }
                },
                upsert=True
            )

if __name__ == "__main__":
    db = get_db()  # Get the MongoDB collection
    shoes = runningwarehouse.scrape_runningwarehouse()  # Scrape the shoe data
    add_shoes_to_db(shoes, db)  # Save the shoes to MongoDB
    print("Shoes saved to MongoDB.")
    collection = db["shoes"]
    total_shoes = collection.count_documents({})  # Count the total documents in the 'shoes' collection
    print(f"Total Shoes in Database: {total_shoes}")
