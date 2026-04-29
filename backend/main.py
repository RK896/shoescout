from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.server_api import ServerApi
from fastapi import FastAPI, Query, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from scraper import nike, newbalance
from scraper import runningwarehouse_api as runningwarehouse
import os
import re
import logging
import json
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from datetime import datetime, timezone
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Sentry initialization
SENTRY_DSN = os.getenv("SENTRY_DSN")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(at_exit=True),
        ],
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )

# Structured JSON Logging
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)

logger = logging.getLogger("shoescout")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger.addHandler(handler)

# Rate limiting setup
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="ShoeScout API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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


def _normalize_text(value) -> str:
    """Normalize free-form text for comparisons."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip().lower()


def _normalize_size_value(value) -> str:
    """Normalize shoe sizes so common fractional formats compare cleanly."""
    text = _normalize_text(value)
    if not text:
        return ""

    text = text.replace("½", ".5").replace("¼", ".25").replace("¾", ".75")
    text = re.sub(r"(\d+)\s*1/2\b", r"\1.5", text)
    text = re.sub(r"(\d+)\s*1/4\b", r"\1.25", text)
    text = re.sub(r"(\d+)\s*3/4\b", r"\1.75", text)
    return text.replace(" ", "")


def _normalize_width_value(value) -> str:
    """Normalize width labels into a small set of comparable buckets."""
    text = _normalize_text(value).replace(" ", "").replace("-", "")
    if not text:
        return "standard"

    if text in {"d", "m", "regular", "medium", "std", "standard"}:
        return "standard"
    if text in {"wide", "w", "2e", "ee", "4e"} or "wide" in text or re.fullmatch(r"\d+e+", text):
        return "wide"
    if text in {"narrow", "b", "c", "aa"} or "narrow" in text:
        return "narrow"
    return text


def _coerce_variant_dict(variant) -> Optional[dict]:
    """Convert a variant-like object into a plain dict."""
    if isinstance(variant, dict):
        return dict(variant)
    if hasattr(variant, "__dict__"):
        return dict(vars(variant))
    return None


def _iter_shoe_variants(shoe: dict) -> list[dict]:
    """Collect variant records from both top-level and retailer-level storage."""
    variants: list[dict] = []
    seen: set[tuple] = set()

    def add_variant(raw_variant, retailer_name: str = "") -> None:
        variant = _coerce_variant_dict(raw_variant)
        if not variant:
            return
        if retailer_name and not variant.get("retailer"):
            variant["retailer"] = retailer_name

        signature = (
            _normalize_size_value(variant.get("size")),
            _normalize_width_value(variant.get("width")),
            _normalize_text(variant.get("link")),
            _normalize_text(variant.get("variant_id")),
            _normalize_text(variant.get("retailer")),
        )
        if signature in seen:
            return
        seen.add(signature)
        variants.append(variant)

    for variant in shoe.get("size_variants", []) or []:
        add_variant(variant)

    for variant in shoe.get("variants", []) or []:
        add_variant(variant)

    for retailer in shoe.get("retailers", []) or []:
        retailer_name = retailer.get("retailer", "")
        for variant in retailer.get("variants", []) or []:
            add_variant(variant, retailer_name=retailer_name)

    return variants


def _merge_variants(existing_variants, incoming_variants) -> list[dict]:
    """Merge two variant lists while keeping order and removing duplicates."""
    merged: list[dict] = []
    seen: set[tuple] = set()

    for raw_variant in list(existing_variants or []) + list(incoming_variants or []):
        variant = _coerce_variant_dict(raw_variant)
        if not variant:
            continue

        signature = (
            _normalize_size_value(variant.get("size")),
            _normalize_width_value(variant.get("width")),
            _normalize_text(variant.get("link")),
            _normalize_text(variant.get("variant_id")),
            _normalize_text(variant.get("retailer")),
        )
        if signature in seen:
            continue
        seen.add(signature)
        merged.append(variant)

    return merged


def _size_matches(size_filter: Optional[str], candidate_size) -> bool:
    if not size_filter:
        return True
    return _normalize_size_value(size_filter) == _normalize_size_value(candidate_size)


def _width_matches(width_filter: Optional[str], candidate_width) -> bool:
    if not width_filter:
        return True
    return _normalize_width_value(width_filter) == _normalize_width_value(candidate_width)


def _shoe_matches_variant_filters(shoe: dict, size: Optional[str] = None, width: Optional[str] = None) -> bool:
    """Return True when any stored variant satisfies the requested size/width."""
    if not size and not width:
        return True

    variants = _iter_shoe_variants(shoe)
    if not variants:
        available_sizes = {_normalize_size_value(s) for s in shoe.get("available_sizes", []) or []}
        available_widths = {_normalize_width_value(w) for w in shoe.get("available_widths", []) or []}

        if size and width:
            return _normalize_size_value(size) in available_sizes and _normalize_width_value(width) in available_widths
        if size:
            return _normalize_size_value(size) in available_sizes
        if width:
            return _normalize_width_value(width) in available_widths
        return False

    for variant in variants:
        if _size_matches(size, variant.get("size")) and _width_matches(width, variant.get("width")):
            return True

    return False


def _variant_metadata(shoe: dict) -> tuple[list[str], list[str]]:
    """Extract lightweight size/width metadata for API responses."""
    variants = _iter_shoe_variants(shoe)
    sizes: list[str] = []
    widths: list[str] = []
    seen_sizes: set[str] = set()
    seen_widths: set[str] = set()

    for variant in variants:
        size = variant.get("size")
        size_key = _normalize_size_value(size)
        if size and size_key and size_key not in seen_sizes:
            seen_sizes.add(size_key)
            sizes.append(str(size).strip())

        width = variant.get("width")
        width_key = _normalize_width_value(width)
        if width_key and width_key not in seen_widths:
            seen_widths.add(width_key)
            if width_key == "standard":
                widths.append("Standard")
            elif width_key == "wide":
                widths.append("Wide")
            elif width_key == "narrow":
                widths.append("Narrow")
            else:
                widths.append(str(width).strip() if width else "Standard")

    if not sizes and shoe.get("available_sizes"):
        sizes = [str(size).strip() for size in shoe.get("available_sizes", []) if str(size).strip()]
    if not widths and shoe.get("available_widths"):
        widths = [str(width).strip() for width in shoe.get("available_widths", []) if str(width).strip()]

    return sizes, widths


def _prepare_shoe_response(shoe: dict, discount_threshold: float = 5.0) -> dict:
    """Add derived fields and remove heavyweight properties before responding."""
    shoe = dict(shoe)

    discount_info = _calculate_shoe_discount(shoe, minimum_discount=discount_threshold)
    if discount_info:
        shoe["discount_pct"] = discount_info["discount_percent"]
        shoe["average_price"] = discount_info["average_price"]

    sizes, widths = _variant_metadata(shoe)
    if sizes:
        shoe["available_sizes"] = sizes
    if widths:
        shoe["available_widths"] = widths

    shoe.pop("price_history", None)

    if "embeddings" in shoe and shoe["embeddings"] is not None:
        if hasattr(shoe["embeddings"], "tolist"):
            shoe["embeddings"] = shoe["embeddings"].tolist()
        elif not isinstance(shoe["embeddings"], list):
            shoe["embeddings"] = list(shoe["embeddings"])

    return shoe


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


@app.get("/admin/status")
def scraper_status(x_admin_key: str = Header(None)):
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key or x_admin_key != admin_key:
        raise HTTPException(status_code=403, detail="Forbidden: invalid or missing admin key")
    try:
        runs_coll = get_db()["scraper_runs"]
        latest = list(runs_coll.find({}, {"_id": 0}).sort("started_at", -1).limit(50))
        by_scraper: dict = {}
        for run in latest:
            name = run.get("scraper")
            if name and name not in by_scraper:
                by_scraper[name] = run
        return {"scrapers": list(by_scraper.values())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
        # Alerts collection indexes
        alerts_coll = get_db()["alerts"]
        alerts_coll.create_index([("email", ASCENDING)], background=True)
        alerts_coll.create_index([("shoe_model", ASCENDING), ("active", ASCENDING)], background=True)
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
    page: int = Query(1, gt=0),
    limit: int = Query(24, gt=0),
    brand: Optional[str] = Query(None),
    retailer: Optional[str] = Query(None),
    gender: Optional[str] = Query(None, description="mens or womens"),
    category: Optional[str] = Query(None, description="road or trail"),
    size: Optional[str] = Query(None, description="Match shoes with this size in stored variants"),
    width: Optional[str] = Query(None, description="Match shoes with this width in stored variants"),
    min_discount: Optional[float] = Query(None, ge=0, le=100, description="Minimum discount percentage")
):
    """Paginated list of shoes with optional brand, retailer, gender, category, size, width, and discount filters."""
    try:
        collection = get_collection()
        skip = (page - 1) * limit
        size_filter = size.strip() if size and size.strip() else None
        width_filter = width.strip() if width and width.strip() else None

        query = {}
        if brand:
            query["brand"] = brand
        if retailer:
            query["retailers.retailer"] = retailer
        if category:
            query["category"] = category.lower()
        if gender:
            if gender.lower() == "mens":
                query["gender"] = {"$regex": "^Men", "$options": "i"}
            elif gender.lower() == "womens":
                query["gender"] = {"$regex": "^Women", "$options": "i"}

        needs_full_filter = bool(size_filter or width_filter or min_discount is not None)

        if needs_full_filter:
            shoes = list(collection.find(query, {"_id": 0}))
            filtered_shoes = []
            response_discount_threshold = min_discount if min_discount is not None else 5.0
            for shoe in shoes:
                if not _shoe_matches_variant_filters(shoe, size=size_filter, width=width_filter):
                    continue

                if min_discount is not None:
                    discount_info = _calculate_shoe_discount(shoe)
                    if not discount_info or discount_info["discount_percent"] < min_discount:
                        continue
                filtered_shoes.append(_prepare_shoe_response(shoe, discount_threshold=response_discount_threshold))

            total_count = len(filtered_shoes)
            shoes = filtered_shoes[skip:skip + limit]
        else:
            total_count = collection.count_documents(query)
            shoes = list(collection.find(query, {"_id": 0}).skip(skip).limit(limit))

            # Ensure all embeddings are lists (not numpy arrays) for JSON serialization
            shoes = [_prepare_shoe_response(shoe) for shoe in shoes]

        # Generate embeddings in batch for shoes that don't have them yet.
        # Cap at 100 per call so they accumulate over time without blocking the request.
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
@limiter.limit("60/minute")
def search_shoes(request: Request, q: str = Query("", description="Search query; empty returns all shoes.")):
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
def scrape_and_store(x_admin_key: str = Header(None)):
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key or x_admin_key != admin_key:
        raise HTTPException(status_code=403, detail="Forbidden: invalid or missing admin key")
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
        from scraper import roadrunnersports_api
        shoes.extend(roadrunnersports_api.scrape_roadrunnersports())
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
    try:
        from scraper import finishline
        shoes.extend(finishline.scrape_finishline())
    except Exception as e:
        print(f"Finish Line scraper failed: {e}")
    try:
        from scraper import asics
        shoes.extend(asics.scrape_asics())
    except Exception as e:
        print(f"ASICS scraper failed: {e}")
    try:
        from scraper import rei
        shoes.extend(rei.scrape_rei())
    except Exception as e:
        print(f"REI scraper failed: {e}")
    try:
        from scraper import on_running
        shoes.extend(on_running.scrape_on())
    except Exception as e:
        print(f"ON Running scraper failed: {e}")
    try:
        from scraper import altra
        shoes.extend(altra.scrape_altra())
    except Exception as e:
        print(f"Altra scraper failed: {e}")
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

        existing_shoe = collection.find_one({"model": shoe_model})
        variant_metadata = _build_variant_metadata(shoe, existing_shoe)

        # Create price history entry
        price_snapshot = {
            "retailer": retailer,
            "price": price,
            "price_value": parse_price(price),
            "timestamp": timestamp
        }

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
                    update_fields = {"retailers.$.price": price}
                    if variant_metadata:
                        update_fields.update(variant_metadata)
                    collection.update_one(
                        {"model": shoe_model, "retailers.retailer": retailer},
                        {"$set": update_fields}
                    )
            else:
                update_doc = {
                    "$addToSet": {
                        "retailers": {
                            "retailer": retailer,
                            "price": price,
                            "link": link
                        }
                    }
                }
                if variant_metadata:
                    update_doc["$set"] = variant_metadata
                collection.update_one(
                    {"model": shoe_model},
                    update_doc
                )
            # Always append to price history
            collection.update_one(
                {"model": shoe_model},
                {"$push": {"price_history": price_snapshot}}
            )
        else:
            set_fields = {
                "brand": brand,
                "model": shoe_model,
                "image": image,
                "gender": shoe.get("gender"),
                "category": shoe.get("category")
            }
            if variant_metadata:
                set_fields.update(variant_metadata)
            collection.update_one(
                {"model": shoe_model},
                {
                    "$set": set_fields,
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


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "available", "in_stock"}
    return bool(value)


def _normalize_variant_entry(raw_variant: dict) -> Optional[dict]:
    if not isinstance(raw_variant, dict):
        return None

    size = str(raw_variant.get("size", "")).strip()
    if not size:
        return None

    return {
        "size": size,
        "width": str(raw_variant.get("width", "")).strip(),
        "price": raw_variant.get("price", ""),
        "list_price": raw_variant.get("list_price", ""),
        "available": _coerce_bool(raw_variant.get("available", False)),
        "variant_id": str(raw_variant.get("variant_id", "")).strip(),
        "link": str(raw_variant.get("link", "")).strip(),
    }


def _variant_identity_key(variant: dict) -> tuple[str, ...]:
    variant_id = variant.get("variant_id", "")
    if variant_id:
        return ("id", variant_id)
    return (
        "variant",
        variant.get("size", "").lower(),
        variant.get("width", "").lower(),
        variant.get("link", ""),
    )


def _merge_variant_entries(existing_variants, incoming_variants) -> list[dict]:
    merged: dict[tuple[str, ...], dict] = {}

    for raw_variant in list(existing_variants or []) + list(incoming_variants or []):
        normalized = _normalize_variant_entry(raw_variant)
        if not normalized:
            continue

        key = _variant_identity_key(normalized)
        current = merged.get(key)
        if current is None:
            merged[key] = normalized
            continue

        current["available"] = current["available"] or normalized["available"]
        if parse_price(str(normalized["price"])) < parse_price(str(current["price"])):
            current["price"] = normalized["price"]
        if parse_price(str(normalized["list_price"])) < parse_price(str(current["list_price"])):
            current["list_price"] = normalized["list_price"]
        if not current["width"] and normalized["width"]:
            current["width"] = normalized["width"]
        if not current["link"] and normalized["link"]:
            current["link"] = normalized["link"]

    return list(merged.values())


def _build_variant_metadata(incoming_shoe: dict, existing_shoe: Optional[dict] = None) -> dict:
    incoming_variants = incoming_shoe.get("size_variants") or incoming_shoe.get("variants") or []
    if not incoming_variants:
        return {}

    existing_variants = []
    if existing_shoe:
        existing_variants = existing_shoe.get("size_variants") or existing_shoe.get("variants") or []

    merged_variants = _merge_variant_entries(existing_variants, incoming_variants)
    return {
        "size_variants": merged_variants,
        "available_sizes": sorted(
            {variant["size"] for variant in merged_variants if variant.get("available") and variant.get("size")}
        ),
        "available_widths": sorted(
            {variant["width"] for variant in merged_variants if variant.get("available") and variant.get("width")}
        ),
    }


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
def scrape_reddit_reviews(x_admin_key: str = Header(None)):
    """Trigger the Reddit review scraper."""
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key or x_admin_key != admin_key:
        raise HTTPException(status_code=403, detail="Forbidden: invalid or missing admin key")
    from scraper.reddit_scraper import scrape_and_store_reviews
    stored = scrape_and_store_reviews(limit=100, include_comments=True)
    return {"message": "reviews scraped and stored", "count": stored}


@app.post("/chat")
@limiter.limit("10/minute")
def chat_endpoint(request: Request, body: dict):
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
        "history": price_history
    }


def _calculate_shoe_discount(shoe: dict, minimum_discount: float = 0.0) -> Optional[dict]:
    """
    Helper to calculate best discount % based on price history.
    Returns a dict with discount_pct, current_price, and average_price or None.
    """
    price_history = shoe.get("price_history", [])
    retailers = shoe.get("retailers", [])

    if not price_history or not retailers:
        return None

    # Calculate average historical price per retailer
    retailer_history = {}
    for entry in price_history:
        retailer_name = entry.get("retailer")
        price_val = entry.get("price_value")
        if retailer_name and price_val and price_val != float('inf'):
            if retailer_name not in retailer_history:
                retailer_history[retailer_name] = []
            retailer_history[retailer_name].append(price_val)

    best_discount = 0.0
    best_retailer = None
    current_price = 0.0
    avg_price = 0.0

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

    if best_discount >= minimum_discount:
        return {
            "retailer": best_retailer,
            "current_price": current_price,
            "average_price": round(avg_price, 2),
            "discount_percent": round(best_discount, 1)
        }
    return None


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
        discount_info = _calculate_shoe_discount(shoe)
        if discount_info and discount_info["discount_percent"] >= min_discount:
            shoe_copy = dict(shoe)
            shoe_copy.pop("price_history", None)
            deals.append({
                **shoe_copy,
                "deal_info": discount_info
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


# ─────────────────────────────────────────────────────────────────────────────
# Price Alert Endpoints
# ─────────────────────────────────────────────────────────────────────────────

class AlertCreateRequest(BaseModel):
    email: str
    shoe_model: str
    target_price: float


def _alerts_collection():
    return get_db()["alerts"]


@app.post("/alerts")
@limiter.limit("20/minute")
def create_alert(request: Request, body: AlertCreateRequest):
    """
    Create a price-drop alert for a shoe.
    The user will receive an email when the shoe's best price falls to
    or below `target_price`.
    """
    email       = body.email.strip().lower()
    shoe_model  = body.shoe_model.strip()
    target_price = round(float(body.target_price), 2)

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email address required.")
    if not shoe_model:
        raise HTTPException(status_code=400, detail="shoe_model is required.")
    if target_price <= 0:
        raise HTTPException(status_code=400, detail="target_price must be greater than 0.")

    # Look up the shoe for extra metadata
    shoe = get_collection().find_one({"model": shoe_model}, {"_id": 0, "brand": 1, "image": 1, "retailers": 1})
    if not shoe:
        raise HTTPException(status_code=404, detail=f"Shoe '{shoe_model}' not found.")

    # Get current best price
    best_price = float("inf")
    for r in shoe.get("retailers", []):
        p = parse_price(r.get("price", ""))
        if p < best_price:
            best_price = p
    current_price = None if best_price == float("inf") else best_price

    # De-duplicate: don't create exact duplicate alert
    alerts_coll = _alerts_collection()
    existing = alerts_coll.find_one({
        "email": email,
        "shoe_model": shoe_model,
        "active": True
    })
    if existing:
        # Update target price if different
        if existing.get("target_price") != target_price:
            alerts_coll.update_one(
                {"_id": existing["_id"]},
                {"$set": {"target_price": target_price}}
            )
            return {
                "message": "Alert updated.",
                "alert_id": str(existing["_id"]),
                "email": email,
                "shoe_model": shoe_model,
                "target_price": target_price,
                "current_price": current_price,
            }
        return {
            "message": "Alert already exists.",
            "alert_id": str(existing["_id"]),
            "email": email,
            "shoe_model": shoe_model,
            "target_price": target_price,
            "current_price": current_price,
        }

    doc = {
        "email": email,
        "shoe_model": shoe_model,
        "shoe_brand": shoe.get("brand", ""),
        "shoe_image": shoe.get("image", ""),
        "target_price": target_price,
        "current_price": current_price,
        "created_at": datetime.now(timezone.utc),
        "last_triggered": None,
        "active": True,
    }
    result = alerts_coll.insert_one(doc)
    return {
        "message": "Alert created. You'll receive an email when the price drops to your target.",
        "alert_id": str(result.inserted_id),
        "email": email,
        "shoe_model": shoe_model,
        "target_price": target_price,
        "current_price": current_price,
    }


@app.get("/alerts")
def list_alerts(email: str = Query(..., description="Email address to look up alerts for")):
    """List all active price alerts for a given email address."""
    email = email.strip().lower()
    alerts_coll = _alerts_collection()
    alerts = list(alerts_coll.find(
        {"email": email, "active": True},
        {"_id": 1, "shoe_model": 1, "shoe_brand": 1, "shoe_image": 1,
         "target_price": 1, "current_price": 1, "created_at": 1, "last_triggered": 1}
    ))
    for a in alerts:
        a["id"] = str(a.pop("_id"))
    return {"email": email, "alerts": alerts}


@app.delete("/alerts/{alert_id}")
def delete_alert(alert_id: str):
    """Cancel (soft-delete) a price alert by ID."""
    alerts_coll = _alerts_collection()
    try:
        oid = ObjectId(alert_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid alert ID.")
    result = alerts_coll.update_one(
        {"_id": oid},
        {"$set": {"active": False}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found.")
    return {"message": "Alert cancelled.", "alert_id": alert_id}


@app.get("/alerts/unsubscribe")
def unsubscribe_alert(id: str = Query(..., description="The ID of the alert to unsubscribe from")):
    """
    Handle unsubscribe requests from email links.
    In a real app, this would return a nice HTML success page.
    """
    alerts_coll = _alerts_collection()
    try:
        oid = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid alert ID.")
    
    result = alerts_coll.update_one(
        {"_id": oid},
        {"$set": {"active": False}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found.")
    
    return {
        "message": "You have been unsubscribed from this price alert.",
        "success": True
    }


@app.post("/alerts/check")
def check_alerts(x_admin_key: str = Header(None)):
    """
    Manually trigger the price-alert checker.
    Called automatically by scrape_runner.py after each scrape cycle.
    Requires X-Admin-Key header.
    """
    admin_key = os.getenv("ADMIN_KEY", "")
    if not admin_key or x_admin_key != admin_key:
        raise HTTPException(status_code=403, detail="Forbidden: invalid or missing admin key")
    from alerts import check_and_fire_alerts
    fired = check_and_fire_alerts(get_db())
    return {"message": f"Alert check complete.", "alerts_fired": fired}
