from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.server_api import ServerApi
from fastapi import FastAPI, Query, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from scraper import nike, newbalance
from scraper import runningwarehouse_api as runningwarehouse
import os
import re
from datetime import datetime, timezone
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
try:
    from embeddings import generate_embeddings, create_shoe_text, model, EMBEDDINGS_AVAILABLE, generate_embeddings_batch, encode_query_via_api, encode_batch_via_api
except Exception as e:
    print(f"Warning: Could not import embeddings module: {e}")
    EMBEDDINGS_AVAILABLE = False
    model = None
    def create_shoe_text(shoe_dict, review_text=None):
        return f"{shoe_dict.get('brand', '')} {shoe_dict.get('model', '')}"
    def encode_query_via_api(query):
        return None
    def encode_batch_via_api(texts, input_type="search_document"):
        return None
import numpy as np

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"]
)


_client = None
_db = None
_collection = None
_indexes_ensured = False

def get_db():
    """Lazy initialization of MongoDB connection (fork-safe)."""
    global _client, _db
    if _db is None:
        uri = os.getenv("MONGO_URI")
        _client = MongoClient(uri, server_api=ServerApi('1'))
        try:
            _client.admin.command('ping')
            print("Pinged your deployment. You successfully connected to MongoDB!")
        except Exception as e:
            print(e)
        _db = _client["shoe_scout"]
    return _db

def get_collection():
    """Get the shoes collection (fork-safe)."""
    global _collection, _indexes_ensured
    if _collection is None:
        _collection = get_db()["shoes"]
    if not _indexes_ensured:
        ensure_indexes()
        _indexes_ensured = True
    return _collection


def parse_price(price_str: str) -> float:
    """Robustly parse a price string to float. Returns inf on failure."""
    if not price_str:
        return float('inf')
    cleaned = price_str.replace(',', '')
    match = re.search(r'[\d]+\.?\d*', cleaned)
    return float(match.group()) if match else float('inf')


@app.get("/")
def read_root():
    return {"message": "ShoeScout API is live!"}


@app.get("/health")
def health_check():
    try:
        get_collection().find_one()
        return {"status": "healthy", "database": "connected", "embeddings": EMBEDDINGS_AVAILABLE}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}


# Note: db and collection are now lazily initialized via get_db() and get_collection()

# Create MongoDB indexes for performance (called lazily on first request)
def ensure_indexes():
    """Create indexes for common query patterns."""
    try:
        # Use _collection directly to avoid recursion
        coll = _collection
        if coll is None:
            return
        coll.create_index([("model", ASCENDING)], unique=True, background=True)
        coll.create_index([("brand", ASCENDING)], background=True)
        coll.create_index([("retailers.price", ASCENDING)], background=True)
        coll.create_index([("price_history.timestamp", DESCENDING)], background=True)
        print("MongoDB indexes ensured")
    except Exception as e:
        print(f"Warning: Could not create indexes: {e}")


def _shoes_for_response(shoes_list):
    """Return shoes with embeddings stripped for JSON response."""
    for s in shoes_list:
        s.pop("embeddings", None)
    return shoes_list


def _text_search_shoes(query: str, limit: int = 100):
    """MongoDB text/regex search on brand, model, retailers when semantic search unavailable."""
    collection = get_collection()
    if not query or not query.strip():
        return list(collection.find({}, {"_id": 0}))
    escaped = re.escape(query.strip())
    if not escaped:
        return list(collection.find({}, {"_id": 0}))
    filter_ = {
        "$or": [
            {"model": {"$regex": escaped, "$options": "i"}},
            {"brand": {"$regex": escaped, "$options": "i"}},
            {"retailers.retailer": {"$regex": escaped, "$options": "i"}},
        ]
    }
    return list(collection.find(filter_, {"_id": 0}).limit(limit))


@app.get("/shoes")
def get_shoes(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(24, ge=1, le=100, description="Items per page")
):
    try:
        collection = get_collection()
        skip = (page - 1) * limit
        total_count = collection.count_documents({})
        shoes = list(collection.find({}, {"_id": 0}).skip(skip).limit(limit))

        # Ensure all embeddings are lists (not numpy arrays) for JSON serialization
        for shoe in shoes:
            if "embeddings" in shoe and shoe["embeddings"] is not None:
                if hasattr(shoe["embeddings"], 'tolist'):
                    shoe["embeddings"] = shoe["embeddings"].tolist()
                elif not isinstance(shoe["embeddings"], list):
                    shoe["embeddings"] = list(shoe["embeddings"])

        # Generate embeddings in batch for shoes that don't have them yet.
        # Cap at 100 per call so they accumulate over time without blocking the request.
        # Tier 1: local sentence-transformers (fast, needs ~500MB RAM)
        # Tier 2: Cohere API batch (reliable, works on free Render tier)
        shoes_needing_embeddings = [s for s in shoes if s.get("embeddings") is None][:100]
        if shoes_needing_embeddings:
            reviews_collection = get_db()["reviews"]
            reviews_by_model = {}
            for shoe in shoes_needing_embeddings:
                model_name = shoe.get("model")
                doc = reviews_collection.find_one({"shoe_model": model_name}, {"reviews": 1})
                if doc and doc.get("reviews"):
                    parts = []
                    for rev in doc["reviews"][:10]:
                        if rev.get("summary"):
                            parts.append(rev["summary"])
                        for p in rev.get("pros", [])[:3]:
                            parts.append(p)
                        for c in rev.get("cons", [])[:3]:
                            parts.append(c)
                    if parts:
                        reviews_by_model[model_name] = " ".join(parts)

            texts = [
                create_shoe_text(shoe, review_text=reviews_by_model.get(shoe.get("model"), ""))
                for shoe in shoes_needing_embeddings
            ]
            embeddings = encode_batch_via_api(texts, input_type="search_document")
            if embeddings:
                for shoe, embedding in zip(shoes_needing_embeddings, embeddings):
                    collection.update_one({"model": shoe["model"]}, {"$set": {"embeddings": embedding}})
                    shoe["embeddings"] = embedding
                print(f"Cohere: generated embeddings for {len(embeddings)} shoes")
        return {
            "shoes": shoes,
            "page": page,
            "limit": limit,
            "total": total_count,
            "total_pages": (total_count + limit - 1) // limit
        }
    except Exception as e:
        print(f"Error in get_shoes: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch shoes: {str(e)}")


@app.get("/search")
def search_shoes(q: str = Query("", description="Search query; empty returns all shoes.")):
    try:
        collection = get_collection()
        if not q or not q.strip():
            all_shoes = list(collection.find({}, {"_id": 0}))
            return _shoes_for_response(all_shoes)

        query_embedding_list = encode_query_via_api(q)
        if query_embedding_list is None:
            print("Semantic search unavailable. Using text search on brand/model/retailer.")
            return _shoes_for_response(_text_search_shoes(q.strip()))
        query_embedding = np.array(query_embedding_list)

        shoes = list(collection.find({"embeddings": {"$exists": True}}, {"_id": 0}))
        if not shoes:
            # No embeddings yet — fall back to text search
            return _shoes_for_response(_text_search_shoes(q.strip()))

        results = []
        for shoe in shoes:
            if "embeddings" not in shoe:
                continue
            try:
                shoe_embedding = np.array(shoe["embeddings"])
                norm_q = np.linalg.norm(query_embedding)
                norm_s = np.linalg.norm(shoe_embedding)
                if norm_q == 0 or norm_s == 0:
                    continue
                similarity = np.dot(query_embedding, shoe_embedding) / (norm_q * norm_s)
                results.append((similarity, shoe))
            except Exception as e:
                print(f"Error processing shoe {shoe.get('model', 'unknown')}: {e}")
                continue

        results.sort(key=lambda x: x[0], reverse=True)
        top = results[:10]
        return _shoes_for_response([shoe for _, shoe in top])
    except HTTPException:
        raise
    except Exception as e:
        print(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.post("/scrape")
def scrape_and_store():
    shoes = []
    try:
        shoes.extend(runningwarehouse.scrape_runningwarehouse())
    except Exception as e:
        print(f"Running Warehouse scraper failed: {e}")
    try:
        shoes.extend(nike.scrape_nike())
    except Exception as e:
        print(f"Nike scraper failed: {e}")
    try:
        shoes.extend(newbalance.scrape_newbalance())
    except Exception as e:
        print(f"New Balance scraper failed: {e}")
    try:
        from scraper import brooks
        shoes.extend(brooks.scrape_brooks())
    except Exception as e:
        print(f"Brooks scraper failed: {e}")
    try:
        from scraper import hoka
        shoes.extend(hoka.scrape_hoka())
    except Exception as e:
        print(f"HOKA scraper failed: {e}")
    try:
        from scraper import saucony_api
        shoes.extend(saucony_api.scrape_saucony())
    except Exception as e:
        print(f"Saucony scraper failed: {e}")
    try:
        from scraper import adidas
        shoes.extend(adidas.scrape_adidas())
    except Exception as e:
        print(f"Adidas scraper failed: {e}")
    try:
        from scraper import zappos_api
        shoes.extend(zappos_api.scrape_zappos())
    except Exception as e:
        print(f"Zappos scraper failed: {e}")
    try:
        from scraper import fleetfeet
        shoes.extend(fleetfeet.scrape_fleetfeet())
    except Exception as e:
        print(f"Fleet Feet scraper failed: {e}")
    try:
        from scraper import roadrunnersports
        shoes.extend(roadrunnersports.scrape_roadrunnersports())
    except Exception as e:
        print(f"Road Runner Sports scraper failed: {e}")
    try:
        from scraper import dicks
        shoes.extend(dicks.scrape_dicks())
    except Exception as e:
        print(f"Dick's Sporting Goods scraper failed: {e}")
    try:
        from scraper import holabird
        shoes.extend(holabird.scrape_holabird())
    except Exception as e:
        print(f"Holabird Sports scraper failed: {e}")
    add_shoes_to_db(shoes, get_db())
    return {"message": "shoes scraped and stored", "count": len(shoes)}


def add_shoes_to_db(shoes, db):
    collection = db["shoes"]
    timestamp = datetime.now(timezone.utc)

    for shoe in shoes:
        shoe_model = shoe["model"]
        brand = shoe["brand"]
        price = shoe["price"]
        image = shoe["image"]
        retailer = shoe["retailer"]
        link = shoe["link"]

        # Skip shoes with no model name
        if not shoe_model or not shoe_model.strip():
            continue

        # Create price history entry
        price_snapshot = {
            "retailer": retailer,
            "price": price,
            "price_value": parse_price(price),
            "timestamp": timestamp
        }

        existing_shoe = collection.find_one({"model": shoe_model})
        if existing_shoe:
            existing_retailer = None
            for retailer_entry in existing_shoe.get("retailers", []):
                if retailer_entry["retailer"] == retailer:
                    existing_retailer = retailer_entry
                    break

            if existing_retailer:
                # Update price if the new one is lower
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
                    {
                        "$addToSet": {
                            "retailers": {
                                "retailer": retailer,
                                "price": price,
                                "link": link
                            }
                        }
                    }
                )
            # Always append to price history
            collection.update_one(
                {"model": shoe_model},
                {"$push": {"price_history": price_snapshot}}
            )
        else:
            collection.update_one(
                {"model": shoe_model},
                {
                    "$set": {
                        "brand": brand,
                        "model": shoe_model,
                        "image": image
                    },
                    "$addToSet": {
                        "retailers": {
                            "retailer": retailer,
                            "price": price,
                            "link": link
                        }
                    },
                    "$push": {
                        "price_history": price_snapshot
                    }
                },
                upsert=True
            )


@app.delete("/reviews")
def clear_all_reviews(x_admin_key: str = Header(None)):
    """Clear all reviews from the database. Requires X-Admin-Key header."""
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key or x_admin_key != admin_key:
        raise HTTPException(status_code=403, detail="Forbidden: invalid or missing admin key")
    reviews_collection = get_db()["reviews"]
    result = reviews_collection.delete_many({})
    return {"message": "All reviews cleared", "deleted_count": result.deleted_count}


@app.post("/scrape_reviews")
def scrape_reddit_reviews():
    from scraper.reddit_scraper import scrape_and_store_reviews
    stored = scrape_and_store_reviews(limit=100, include_comments=True)
    return {"message": "reviews scraped and stored", "count": stored}


@app.post("/chat")
def chat_endpoint(body: dict):
    """AI shoe recommendation chatbot powered by Claude."""
    collection = get_collection()
    message = body.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    # Find relevant shoes using semantic or text search
    try:
        query_embedding = None
        if EMBEDDINGS_AVAILABLE:
            query_embedding = np.array(model.encode(message))
        else:
            query_embedding_list = encode_query_via_api(message)
            if query_embedding_list is not None:
                query_embedding = np.array(query_embedding_list)

        if query_embedding is not None:
            shoes = list(collection.find({"embeddings": {"$exists": True}}, {"_id": 0}))
            results = []
            for shoe in shoes:
                try:
                    shoe_embedding = np.array(shoe["embeddings"])
                    norm_q = np.linalg.norm(query_embedding)
                    norm_s = np.linalg.norm(shoe_embedding)
                    if norm_q == 0 or norm_s == 0:
                        continue
                    similarity = np.dot(query_embedding, shoe_embedding) / (norm_q * norm_s)
                    results.append((similarity, shoe))
                except Exception:
                    continue
            results.sort(key=lambda x: x[0], reverse=True)
            relevant_shoes = [shoe for _, shoe in results[:8]]
        else:
            relevant_shoes = _text_search_shoes(message, limit=8)
    except Exception as e:
        print(f"Chat search error: {e}")
        relevant_shoes = _text_search_shoes(message, limit=8)

    # Fetch reviews for relevant shoes
    reviews_collection = get_db()["reviews"]
    shoes_with_reviews = []
    for shoe in relevant_shoes:
        shoe_data = dict(shoe)
        shoe_data.pop("embeddings", None)
        review_doc = reviews_collection.find_one(
            {"shoe_model": shoe.get("model")},
            {"_id": 0, "reviews": 1}
        )
        if review_doc:
            shoe_data["reviews"] = review_doc.get("reviews", [])[:3]
        else:
            shoe_data["reviews"] = []
        shoes_with_reviews.append(shoe_data)

    from chat import get_shoe_recommendation
    response = get_shoe_recommendation(message, shoes_with_reviews)
    return {"response": response}


def _get_reviews_for_shoe_impl(shoe_model: str):
    """Shared impl for path and query param."""
    reviews_collection = get_db()["reviews"]
    shoe_review = reviews_collection.find_one(
        {"shoe_model": shoe_model},
        {"_id": 0}
    )
    if shoe_review:
        reviews = shoe_review.get("reviews", [])
        # Sort by upvote score so highest quality reviews appear first
        reviews.sort(key=lambda r: r.get("post_score", 0), reverse=True)

        from review_summarizer import generate_summary
        from sentiment_analyzer import extract_pros_cons

        for review in reviews:
            needs_update = False
            update_fields = {}

            if "summary" not in review or not review.get("summary"):
                summary = generate_summary(review.get("post_text", ""), shoe_model=shoe_model)
                if summary:
                    review["summary"] = summary
                    update_fields["reviews.$.summary"] = summary
                    needs_update = True

            if "pros" not in review or "cons" not in review:
                pros_cons = extract_pros_cons(review.get("post_text", ""), shoe_model=shoe_model)
                if pros_cons.get("pros") or pros_cons.get("cons"):
                    review["pros"] = pros_cons.get("pros", [])
                    review["cons"] = pros_cons.get("cons", [])
                    update_fields["reviews.$.pros"] = pros_cons.get("pros", [])
                    update_fields["reviews.$.cons"] = pros_cons.get("cons", [])
                    needs_update = True

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
    reviews_collection = get_db()["reviews"]
    all_reviews = list(reviews_collection.find({}, {"_id": 0}))
    return all_reviews


@app.get("/shoes/{shoe_model:path}/price-history")
def get_price_history(shoe_model: str):
    """Get price history for a specific shoe model."""
    collection = get_collection()
    shoe = collection.find_one({"model": shoe_model}, {"_id": 0, "price_history": 1, "model": 1})
    if not shoe:
        raise HTTPException(status_code=404, detail=f"Shoe '{shoe_model}' not found")

    price_history = shoe.get("price_history", [])
    # Sort by timestamp descending (most recent first)
    price_history.sort(key=lambda x: x.get("timestamp", datetime.min), reverse=True)

    return {
        "model": shoe_model,
        "price_history": price_history
    }


@app.get("/deals")
def get_deals(
    min_discount: float = Query(15.0, ge=0, le=100, description="Minimum discount percentage"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of deals to return")
):
    """
    Returns shoes where any retailer's current price is at least min_discount%
    below the historical average price. Sorted by discount percentage (highest first).
    """
    collection = get_collection()
    shoes = list(collection.find(
        {"price_history": {"$exists": True, "$ne": []}},
        {"_id": 0, "embeddings": 0}
    ))

    deals = []
    for shoe in shoes:
        price_history = shoe.get("price_history", [])
        retailers = shoe.get("retailers", [])

        if not price_history or not retailers:
            continue

        # Calculate average historical price per retailer
        retailer_history = {}
        for entry in price_history:
            retailer_name = entry.get("retailer")
            price_val = entry.get("price_value")
            if retailer_name and price_val and price_val != float('inf'):
                if retailer_name not in retailer_history:
                    retailer_history[retailer_name] = []
                retailer_history[retailer_name].append(price_val)

        # Find best deal among all retailers
        best_discount = 0
        best_retailer = None
        current_price = None
        avg_price = None

        for retailer in retailers:
            retailer_name = retailer.get("retailer")
            current_price_val = parse_price(retailer.get("price", ""))

            if retailer_name in retailer_history and current_price_val != float('inf'):
                prices = retailer_history[retailer_name]
                if len(prices) >= 1:
                    historical_avg = sum(prices) / len(prices)
                    if historical_avg > 0:
                        discount = ((historical_avg - current_price_val) / historical_avg) * 100
                        if discount > best_discount:
                            best_discount = discount
                            best_retailer = retailer_name
                            current_price = current_price_val
                            avg_price = historical_avg

        if best_discount >= min_discount:
            shoe_copy = dict(shoe)
            shoe_copy.pop("price_history", None)  # Don't include full history in response
            deals.append({
                **shoe_copy,
                "deal_info": {
                    "retailer": best_retailer,
                    "current_price": current_price,
                    "average_price": round(avg_price, 2),
                    "discount_percent": round(best_discount, 1)
                }
            })

    # Sort by discount percentage (highest first)
    deals.sort(key=lambda x: x["deal_info"]["discount_percent"], reverse=True)

    return deals[:limit]


@app.get("/brands")
def get_brands():
    """Returns list of distinct brands with count of models for each."""
    collection = get_collection()
    pipeline = [
        {"$group": {
            "_id": "$brand",
            "count": {"$sum": 1}
        }},
        {"$match": {"_id": {"$ne": None}}},
        {"$sort": {"count": -1}}
    ]

    result = list(collection.aggregate(pipeline))

    brands = [
        {"brand": item["_id"], "model_count": item["count"]}
        for item in result
    ]

    return {
        "brands": brands,
        "total_brands": len(brands)
    }


@app.get("/shoes/{shoe_model:path}/similar")
def get_similar_shoes(shoe_model: str, limit: int = Query(5, ge=1, le=20)):
    """
    Returns similar shoes based on embedding similarity.
    Uses the same embedding logic as search.
    """
    collection = get_collection()
    # Find the target shoe
    target_shoe = collection.find_one({"model": shoe_model}, {"_id": 0})
    if not target_shoe:
        raise HTTPException(status_code=404, detail=f"Shoe '{shoe_model}' not found")

    target_embedding = target_shoe.get("embeddings")

    # If target shoe has no embedding, try to generate one
    if target_embedding is None and EMBEDDINGS_AVAILABLE:
        try:
            reviews_collection = get_db()["reviews"]
            review_doc = reviews_collection.find_one({"shoe_model": shoe_model}, {"reviews": 1})
            review_text = ""
            if review_doc and review_doc.get("reviews"):
                parts = []
                for rev in review_doc["reviews"][:10]:
                    if rev.get("summary"):
                        parts.append(rev["summary"])
                    for p in rev.get("pros", [])[:3]:
                        parts.append(p)
                    for c in rev.get("cons", [])[:3]:
                        parts.append(c)
                if parts:
                    review_text = " ".join(parts)
            target_embedding = generate_embeddings(target_shoe, review_text=review_text)
            if target_embedding:
                collection.update_one(
                    {"model": shoe_model},
                    {"$set": {"embeddings": target_embedding}}
                )
        except Exception as e:
            print(f"Error generating embedding for {shoe_model}: {e}")

    if target_embedding is None:
        # Fall back to brand-based similarity
        same_brand_shoes = list(collection.find(
            {"brand": target_shoe.get("brand"), "model": {"$ne": shoe_model}},
            {"_id": 0, "embeddings": 0}
        ).limit(limit))
        return _shoes_for_response(same_brand_shoes)

    target_embedding = np.array(target_embedding)

    # Find all shoes with embeddings
    shoes = list(collection.find(
        {"embeddings": {"$exists": True}, "model": {"$ne": shoe_model}},
        {"_id": 0}
    ))

    if not shoes:
        # Fall back to brand-based similarity
        same_brand_shoes = list(collection.find(
            {"brand": target_shoe.get("brand"), "model": {"$ne": shoe_model}},
            {"_id": 0, "embeddings": 0}
        ).limit(limit))
        return _shoes_for_response(same_brand_shoes)

    # Calculate similarity scores
    results = []
    for shoe in shoes:
        try:
            shoe_embedding = np.array(shoe["embeddings"])
            norm_t = np.linalg.norm(target_embedding)
            norm_s = np.linalg.norm(shoe_embedding)
            if norm_t == 0 or norm_s == 0:
                continue
            similarity = np.dot(target_embedding, shoe_embedding) / (norm_t * norm_s)
            results.append((similarity, shoe))
        except Exception as e:
            print(f"Error processing shoe {shoe.get('model', 'unknown')}: {e}")
            continue

    results.sort(key=lambda x: x[0], reverse=True)
    top_similar = [shoe for _, shoe in results[:limit]]

    return _shoes_for_response(top_similar)
