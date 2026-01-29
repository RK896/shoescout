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
    from embeddings import generate_embeddings, create_shoe_text, model, EMBEDDINGS_AVAILABLE, generate_embeddings_batch, encode_query_via_api
except Exception as e:
    print(f"Warning: Could not import embeddings module: {e}")
    EMBEDDINGS_AVAILABLE = False
    model = None
    def generate_embeddings(shoe_dict, review_text=None):
        raise ImportError("Embeddings not available")
    def generate_embeddings_batch(shoe_dicts, reviews_by_model=None):
        raise ImportError("Embeddings not available")
    def create_shoe_text(shoe_dict, review_text=None):
        return f"{shoe_dict.get('brand', '')} {shoe_dict.get('model', '')}"
    def encode_query_via_api(query):
        return None
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
        # Include Reddit review data so semantic search matches "comfortable", "daily trainer", etc.
        if EMBEDDINGS_AVAILABLE:
            shoes_needing_embeddings = [s for s in shoes if s.get("embeddings") is None][:20]
            if shoes_needing_embeddings:
                # Fetch review text per shoe model from reviews collection
                reviews_collection = db["reviews"]
                reviews_by_model = {}
                for shoe in shoes_needing_embeddings:
                    model_name = shoe.get("model")
                    doc = reviews_collection.find_one({"shoe_model": model_name}, {"reviews": 1})
                    if doc and doc.get("reviews"):
                        parts = []
                        for rev in doc["reviews"][:10]:  # up to 10 reviews
                            if rev.get("summary"):
                                parts.append(rev["summary"])
                            for p in rev.get("pros", [])[:3]:
                                parts.append(p)
                            for c in rev.get("cons", [])[:3]:
                                parts.append(c)
                        if parts:
                            reviews_by_model[model_name] = " ".join(parts)
                try:
                    embeddings = generate_embeddings_batch(shoes_needing_embeddings, reviews_by_model=reviews_by_model)
                    for shoe, embedding in zip(shoes_needing_embeddings, embeddings):
                        collection.update_one({"model": shoe["model"]}, {"$set": {"embeddings": embedding}})
                        shoe["embeddings"] = embedding
                except Exception as e:
                    print(f"Error generating embeddings batch: {e}")
                    for shoe in shoes_needing_embeddings:
                        try:
                            review_text = reviews_by_model.get(shoe.get("model"), "")
                            embedding = generate_embeddings(shoe, review_text=review_text)
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
    try:
        if EMBEDDINGS_AVAILABLE:
            query_embedding = np.array(model.encode(q))
        else:
            # Use Hugging Face Inference API when local model disabled (e.g. Render 512MB)
            query_embedding_list = encode_query_via_api(q)
            if query_embedding_list is None:
                # Fallback: return first 10 shoes so UI doesn't break (e.g. missing HF key)
                print("Semantic search unavailable (remote encode failed). Returning fallback results.")
                fallback = list(collection.find({}, {"_id": 0}).limit(10))
                for s in fallback:
                    s.pop("embeddings", None)
                return fallback
            query_embedding = np.array(query_embedding_list)
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
        top = results[:10]
        for _, shoe in top:
            shoe.pop("embeddings", None)
        return [shoe for _, shoe in top]
    except HTTPException:
        raise
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
    stored = scrape_and_store_reviews(limit=100, include_comments=True)
    return {"message": "reviews scraped and stored", "count": stored}

def _get_reviews_for_shoe_impl(shoe_model: str):
    """Shared impl for path and query param."""
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

@app.get("/reviews/{shoe_model:path}")
def get_reviews_for_shoe_path(shoe_model: str):
    """Get reviews by path (use ?shoe_model= for names with slashes, e.g. S/Lab)."""
    return _get_reviews_for_shoe_impl(shoe_model)

@app.get("/reviews")
def get_reviews(shoe_model: str = None):
    """Get all reviews grouped by shoe, or reviews for one shoe if shoe_model query provided."""
    if shoe_model is not None:
        return _get_reviews_for_shoe_impl(shoe_model)
    reviews_collection = db["reviews"]
    all_reviews = list(reviews_collection.find({}, {"_id": 0}))
    return all_reviews

