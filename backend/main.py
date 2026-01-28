from pymongo import MongoClient
from pymongo.server_api import ServerApi
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from scraper import nike, runningwarehouse, newbalance
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
try:
    from embeddings import generate_embeddings, create_shoe_text, model, EMBEDDINGS_AVAILABLE, generate_embeddings_batch
except Exception as e:
    print(f"Warning: Could not import embeddings module: {e}")
    EMBEDDINGS_AVAILABLE = False
    model = None
    def generate_embeddings(shoe_dict):
        raise ImportError("Embeddings not available")
    def generate_embeddings_batch(shoe_dicts):
        raise ImportError("Embeddings not available")
    def create_shoe_text(shoe_dict):
        return f"{shoe_dict.get('brand', '')} {shoe_dict.get('model', '')}"
import numpy as np

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

@app.get("/health")
def health_check():
    try:
        # Test database connection
        collection.find_one()
        return {"status": "healthy", "database": "connected", "embeddings": EMBEDDINGS_AVAILABLE}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}

db = get_db()
collection = db["shoes"]

@app.get("/shoes")
def get_shoes():
    try:
        shoes = list(collection.find({}, {"_id": 0}))
        
        # Ensure all embeddings are lists (not numpy arrays) for JSON serialization
        for shoe in shoes:
            if "embeddings" in shoe and shoe["embeddings"] is not None:
                if hasattr(shoe["embeddings"], 'tolist'):
                    shoe["embeddings"] = shoe["embeddings"].tolist()
                elif not isinstance(shoe["embeddings"], list):
                    # Convert any other array-like to list
                    shoe["embeddings"] = list(shoe["embeddings"])
        
        # Generate embeddings in batch (much faster than one-by-one)
        # Only generate for first 20 shoes without embeddings to avoid blocking
        if EMBEDDINGS_AVAILABLE:
            shoes_needing_embeddings = [s for s in shoes if s.get("embeddings") is None][:20]
            if shoes_needing_embeddings:
                try:
                    # Batch process - much faster!
                    embeddings = generate_embeddings_batch(shoes_needing_embeddings)
                    for shoe, embedding in zip(shoes_needing_embeddings, embeddings):
                        # embeddings are already lists from generate_embeddings_batch
                        collection.update_one({"model": shoe["model"]}, {"$set": {"embeddings": embedding}})
                        # Update in the returned list too
                        shoe["embeddings"] = embedding
                except Exception as e:
                    print(f"Error generating embeddings batch: {e}")
                    # Fallback to individual generation
                    for shoe in shoes_needing_embeddings:
                        try:
                            embedding = generate_embeddings(shoe)
                            # embedding is already a list from generate_embeddings
                            collection.update_one({"model": shoe["model"]}, {"$set": {"embeddings": embedding}})
                            shoe["embeddings"] = embedding
                        except Exception as e2:
                            print(f"Error generating embedding for {shoe.get('model', 'unknown')}: {e2}")
                            continue
        return shoes
    except Exception as e:
        print(f"Error in get_shoes: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch shoes: {str(e)}")

@app.get("/search")
def search_shoes(q: str=Query(...)):
    if not EMBEDDINGS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Semantic search not available. Please upgrade sentence-transformers package.")
    try:
        query_embedding = model.encode(q)
        shoes = list(collection.find({"embeddings": {"$exists": True}}, {"_id": 0}))

        if not shoes:
            return []

        results = []
        for shoe in shoes:
            if "embeddings" not in shoe:
                continue
            try:
                shoe_embedding = np.array(shoe["embeddings"])
                similarity = np.dot(query_embedding, shoe_embedding)/(np.linalg.norm(query_embedding)*np.linalg.norm(shoe_embedding))
                results.append((similarity, shoe))
            except Exception as e:
                print(f"Error processing shoe {shoe.get('model', 'unknown')}: {e}")
                continue
        
        results.sort(key=lambda x: x[0], reverse=True)
        return [shoe for _,shoe in results[:10]] #return top 10 matches
    except Exception as e:
        print(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

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

@app.delete("/reviews")
def clear_all_reviews():
    """Clear all reviews from the database"""
    reviews_collection = db["reviews"]
    result = reviews_collection.delete_many({})
    return {"message": "All reviews cleared", "deleted_count": result.deleted_count}

@app.post("/scrape_reviews")
def scrape_reddit_reviews():
    from scraper.reddit_scraper import scrape_and_store_reviews
    stored = scrape_and_store_reviews(limit=10)
    return {"message": "reviews scraped and stored", "count": stored}

@app.get("/reviews/{shoe_model}")
def get_reviews_for_shoe(shoe_model: str):
    """Get all Reddit reviews for a specific shoe model with summaries"""
    reviews_collection = db["reviews"]
    shoe_review = reviews_collection.find_one(
        {"shoe_model": shoe_model},
        {"_id": 0}
    )
    if shoe_review:
        reviews = shoe_review.get("reviews", [])
        # Summaries and pros/cons are already stored in the database
        # If a review doesn't have them (old data), generate on-the-fly and save
        from review_summarizer import generate_summary
        from sentiment_analyzer import extract_pros_cons
        
        for review in reviews:
            needs_update = False
            update_fields = {}
            
            # Generate summary if missing
            if "summary" not in review or not review.get("summary"):
                summary = generate_summary(review.get("post_text", ""))
                if summary:
                    review["summary"] = summary
                    update_fields["reviews.$.summary"] = summary
                    needs_update = True
            
            # Generate pros/cons if missing
            if "pros" not in review or "cons" not in review:
                pros_cons = extract_pros_cons(review.get("post_text", ""))
                if pros_cons.get("pros") or pros_cons.get("cons"):
                    review["pros"] = pros_cons.get("pros", [])
                    review["cons"] = pros_cons.get("cons", [])
                    update_fields["reviews.$.pros"] = pros_cons.get("pros", [])
                    update_fields["reviews.$.cons"] = pros_cons.get("cons", [])
                    needs_update = True
            
            # Update database if needed
            if needs_update:
                reviews_collection.update_one(
                    {
                        "shoe_model": shoe_model,
                        "reviews.post_url": review.get("post_url")
                    },
                    {"$set": update_fields}
                )
        return reviews
    return []

@app.get("/reviews")
def get_all_reviews():
    """Get all reviews grouped by shoe"""
    reviews_collection = db["reviews"]
    all_reviews = list(reviews_collection.find({}, {"_id": 0}))
    return all_reviews

