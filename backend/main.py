from pymongo import MongoClient
from pymongo.server_api import ServerApi
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from scraper import nike, runningwarehouse, newbalance
import os
from embeddings import generate_embeddings, create_shoe_text

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins = ["*"],
    allow_credentials = True,
    allow_methods=["*"],
    allow_headers=["*"]
    )


def get_db(): 
    uri = os.getenv("MONGO_URI")
    client = MongoClient(uri, server_api=ServerApi('1'))
    try:
        client.admin.command('ping')
        print("Pinged your deployment. You successfully connected to MongoDB!")
    except Exception as e:
        print(e)
    
    db = client["shoe_scout"]
    return db

@app.get("/")
def read_root():
    return {"message": "ShoeScout API is live!"}

db = get_db()
collection = db["shoes"]

@app.get("/shoes")
def get_shoes():
    shoes = list(collection.find({}, {"_id": 0}))
    for shoe in shoes:
        if shoe.get("embeddings") is None:
            shoe["embeddings"] = generate_embeddings(shoe)
            collection.update_one({"model": shoe["model"]}, {"$set": {"embeddings": shoe["embeddings"]}})
    return shoes

@app.get("/search")
def search_shoes(query: str=Query(...)):
    query_embedding = generate_embeddings(query)
    cosine_similarities = np.dot(query_embedding, np.array(collection.find_one({"model": query})["embeddings"]))
    return cosine_similaritiesdid

@app.post("/scrape")
def scrape_and_store():
    shoes = runningwarehouse.scrape_runningwarehouse()
    shoes.extend(nike.scrape_nike())
    shoes.extend(newbalance.scrape_newbalance())
    add_shoes_to_db(shoes, db)  
    return {"message": "shoes scraped and stored", "count": len(shoes)}


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
            for retailer_entry in existing_shoe.get("retailers", []):
                if retailer_entry["retailer"] == retailer:
                    existing_retailer = retailer_entry
                    break

            if existing_retailer:
                existing_price = float(existing_retailer["price"].replace("$", ""))
                new_price = float(price.replace("$", ""))

                if new_price < existing_price:
                    collection.update_one({"model": model, "retailers.retailer": retailer}, 
                                          {"$set": {
                                              "retailers.$.price": price
                                          }})
            else:
                collection.update_one({"model": model}, 
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
                {"model": model},
                {
                    "$set": {
                        "brand": brand,
                        "model": model,
                        "image": image
                    },
                    "$addToSet": {
                        "retailers": {
                            "retailer": retailer,
                            "price": price,
                            "link": link
                        }
                    }
                },
                upsert=True
            )

