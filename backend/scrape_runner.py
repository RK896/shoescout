"""
Standalone scraper runner used by GitHub Actions (scraper.yaml).
Imports scrapers directly and writes to MongoDB without starting the FastAPI app.

Scrapers:
- API-based (fast, no browser): Running Warehouse, Dick's, Zappos, Holabird,
  Saucony, Road Runner Sports, ASICS, REI, ON Running, Altra
- Selenium-based (slower, needs browser): Nike, New Balance, Brooks, HOKA,
  Adidas, Fleet Feet, Finish Line
"""
import os
import re
import importlib
from datetime import datetime, timezone
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


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "available", "in_stock"}
    return bool(value)


def _normalize_variant_entry(raw_variant: dict) -> dict | None:
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


def _build_variant_metadata(incoming_shoe: dict, existing_shoe: dict | None = None) -> dict:
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
        variant_metadata = _build_variant_metadata(shoe, existing_shoe)
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
                    update_fields = {"retailers.$.price": price}
                    if variant_metadata:
                        update_fields.update(variant_metadata)
                    collection.update_one(
                        {"model": shoe_model, "retailers.retailer": retailer},
                        {"$set": update_fields}
                    )
            else:
                update_doc = {
                    "$addToSet": {"retailers": {"retailer": retailer, "price": price, "link": link}}
                }
                if variant_metadata:
                    update_doc["$set"] = variant_metadata
                collection.update_one(
                    {"model": shoe_model},
                    update_doc
                )
        else:
            set_fields = {"brand": brand, "model": shoe_model, "image": image}
            if variant_metadata:
                set_fields.update(variant_metadata)
            collection.update_one(
                {"model": shoe_model},
                {
                    "$set": set_fields,
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
        # API-based scrapers (faster, no Selenium needed)
        ("Running Warehouse", "scraper.runningwarehouse_api", "scrape_runningwarehouse"),
        ("Dick's Sporting Goods", "scraper.dicks", "scrape_dicks"),
        ("Zappos", "scraper.zappos_api", "scrape_zappos"),
        ("Holabird Sports", "scraper.holabird", "scrape_holabird"),
        ("Saucony", "scraper.saucony_api", "scrape_saucony"),
        ("Road Runner Sports", "scraper.roadrunnersports_api", "scrape_roadrunnersports"),
        ("Finish Line", "scraper.finishline", "scrape_finishline"),
        ("ASICS", "scraper.asics", "scrape_asics"),
        ("REI", "scraper.rei", "scrape_rei"),
        ("ON Running", "scraper.on_running", "scrape_on"),
        ("Altra", "scraper.altra", "scrape_altra"),
        # Selenium-based scrapers
        ("Nike", "scraper.nike", "scrape_nike"),
        ("New Balance", "scraper.newbalance", "scrape_newbalance"),
        ("Brooks", "scraper.brooks", "scrape_brooks"),
        ("HOKA", "scraper.hoka", "scrape_hoka"),
        ("Adidas", "scraper.adidas", "scrape_adidas"),
        ("Fleet Feet", "scraper.fleetfeet", "scrape_fleetfeet"),
    ]

    runs_coll = db["scraper_runs"]

    for name, module_path, func_name in scrapers:
        started_at = datetime.now(timezone.utc)
        try:
            module = importlib.import_module(module_path)
            func = getattr(module, func_name)
            shoes = func()
            finished_at = datetime.now(timezone.utc)
            print(f"{name}: scraped {len(shoes)} shoes")
            all_shoes.extend(shoes)
            runs_coll.insert_one({
                "scraper": name,
                "status": "success",
                "count": len(shoes),
                "started_at": started_at,
                "finished_at": finished_at,
                "error": None,
            })
        except Exception as e:
            finished_at = datetime.now(timezone.utc)
            print(f"{name} scraper failed: {e}")
            runs_coll.insert_one({
                "scraper": name,
                "status": "error",
                "count": 0,
                "started_at": started_at,
                "finished_at": finished_at,
                "error": str(e),
            })

    add_shoes_to_db(all_shoes, collection)
    print(f"\nTotal scraped: {len(all_shoes)} shoes stored/updated in MongoDB")

    # Check price alerts and fire emails
    try:
        from alerts import check_and_fire_alerts
        check_and_fire_alerts(db)
    except Exception as e:
        print(f"Alert check failed (non-fatal): {e}")

    return len(all_shoes)


if __name__ == "__main__":
    run_all_scrapers()
