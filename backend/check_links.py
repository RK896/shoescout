"""
Pre-launch sanity check: scan all shoes in MongoDB for broken images and retailer links.
Run manually before launch: python3 check_links.py

Exits with code 1 if any broken links are found.
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv

load_dotenv()

TIMEOUT = 10
MAX_WORKERS = 20
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ShoeScout link checker)"}


def check_url(url: str) -> tuple[str, int | None, str | None]:
    if not url or not url.startswith("http"):
        return url, None, "invalid URL"
    try:
        resp = requests.head(url, timeout=TIMEOUT, headers=HEADERS, allow_redirects=True)
        if resp.status_code >= 400:
            return url, resp.status_code, f"HTTP {resp.status_code}"
        return url, resp.status_code, None
    except requests.RequestException as e:
        return url, None, str(e)


def main():
    uri = os.getenv("MONGO_URI")
    if not uri:
        print("ERROR: MONGO_URI not set")
        sys.exit(1)

    client = MongoClient(uri, server_api=ServerApi("1"))
    shoes = list(client["shoe_scout"]["shoes"].find({}, {"_id": 0, "model": 1, "image": 1, "retailers": 1}))
    print(f"Checking {len(shoes)} shoes...")

    tasks: list[tuple[str, str]] = []
    for shoe in shoes:
        model = shoe.get("model", "unknown")
        if shoe.get("image"):
            tasks.append((f"[image] {model}", shoe["image"]))
        for r in shoe.get("retailers", []):
            if r.get("link"):
                tasks.append((f"[link/{r.get('retailer', '?')}] {model}", r["link"]))

    print(f"Checking {len(tasks)} URLs with {MAX_WORKERS} workers...\n")

    broken: list[tuple[str, str, str]] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        future_to_label = {pool.submit(check_url, url): label for label, url in tasks}
        for future in as_completed(future_to_label):
            label = future_to_label[future]
            url, status, error = future.result()
            if error:
                broken.append((label, url, error))
                print(f"  BROKEN  {label}: {error}")

    print(f"\n{'='*60}")
    if broken:
        print(f"FAILED: {len(broken)} broken URL(s) found")
        for label, url, error in broken:
            print(f"  - {label}\n    {url}\n    {error}")
        sys.exit(1)
    else:
        print(f"OK: all {len(tasks)} URLs returned valid responses")


if __name__ == "__main__":
    main()
