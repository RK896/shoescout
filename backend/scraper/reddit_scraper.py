"""
Reddit scraper for running shoe reviews.

Uses Reddit's JSON API with a compliant API-style user-agent.
No OAuth required for public read-only data.

Sources:
  - r/RunningShoeGeeks: hot, top/week, top/month
  - r/running: search for shoe review posts

Each matched review goes through a single Claude call that:
  1. Verifies the text is a genuine first-hand review of the matched shoe
  2. Extracts specific pros/cons
  3. Writes a concise summary

Falls back to keyword extraction if Claude is unavailable.
"""
import re
import time
import json
import os
import requests
from rapidfuzz import fuzz
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

# Reddit requires a non-browser user-agent for their API endpoints.
# Format: <platform>:<app_id>:<version> (by /u/<username>)
_HEADERS = {
    "User-Agent": "python:shoescout:v1.0 (by /u/shoescout_app)",
    "Accept": "application/json",
}

# Posts matching these patterns are almost certainly not reviews
_NON_REVIEW_RE = re.compile(
    r"\b(wtb|wts|fs:|for sale|giveaway|give away|"
    r"where (can|do) i (buy|find|get)|where to buy|"
    r"which shoe should|what shoe|help me choose|"
    r"first (shoe|running shoe)|beginner)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Reddit fetching helpers
# ---------------------------------------------------------------------------

def _fetch_reddit_listing(url: str, params: dict, retries: int = 3) -> list[dict]:
    """Fetch and parse a Reddit listing JSON with retry + backoff."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, headers=_HEADERS, timeout=15)
            if resp.status_code == 429:
                wait = 10 * (attempt + 1)
                print(f"  Rate limited — waiting {wait}s before retry {attempt + 1}/{retries}")
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                print(f"  Reddit {url} returned {resp.status_code}")
                return []
            data = resp.json()
            posts = []
            for child in data["data"]["children"]:
                try:
                    d = child["data"]
                    if d.get("score", 0) < 3:
                        continue
                    posts.append({
                        "title": d["title"],
                        "selftext": d.get("selftext", ""),
                        "created_utc": d["created_utc"],
                        "score": d["score"],
                        "permalink": d["permalink"],
                        "url": f"https://www.reddit.com{d['permalink']}",
                    })
                except Exception as e:
                    print(f"  Post parse error: {e}")
            return posts
        except Exception as e:
            print(f"  Reddit fetch error ({url}): {e}")
            if attempt < retries - 1:
                time.sleep(5)
    return []


def fetch_all_posts(limit: int = 100) -> list[dict]:
    """
    Collect posts from multiple Reddit sources and deduplicate by permalink.

    Sources:
      - r/RunningShoeGeeks: hot, top/week, top/month
      - r/running: search for shoe review posts
    """
    seen_permalinks = set()
    all_posts = []

    sources = [
        ("https://www.reddit.com/r/RunningShoeGeeks/hot.json",  {"limit": limit}),
        ("https://www.reddit.com/r/RunningShoeGeeks/top.json",  {"limit": limit, "t": "week"}),
        ("https://www.reddit.com/r/RunningShoeGeeks/top.json",  {"limit": limit, "t": "month"}),
        ("https://www.reddit.com/r/running/search.json",
         {"q": "shoe review OR shoe miles OR running shoe", "sort": "top",
          "t": "month", "restrict_sr": 1, "limit": 50}),
    ]

    for url, params in sources:
        posts = _fetch_reddit_listing(url, params)
        added = 0
        for p in posts:
            if p["permalink"] not in seen_permalinks:
                seen_permalinks.add(p["permalink"])
                all_posts.append(p)
                added += 1
        label = url.split("/r/")[1].split("/")[0]
        print(f"  {label} → {added} new posts (running total: {len(all_posts)})")
        time.sleep(2)  # be polite — Reddit allows ~60 req/min unauthenticated

    return all_posts


def fetch_comments(permalink: str) -> list[dict]:
    """Fetch top-level comments for a post (sorted by score desc)."""
    url = f"https://www.reddit.com{permalink}.json"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=12)
        if resp.status_code != 200:
            return []
        data = resp.json()
        comments = []
        if len(data) > 1:
            for item in data[1]["data"]["children"]:
                if item["kind"] != "t1":
                    continue
                d = item["data"]
                body = d.get("body", "")
                if not body or body in ("[deleted]", "[removed]"):
                    continue
                comments.append({
                    "body": body,
                    "score": d.get("score", 0),
                    "created_utc": d.get("created_utc", 0),
                    "permalink": f"https://www.reddit.com{d.get('permalink', permalink)}",
                })
        return sorted(comments, key=lambda c: c["score"], reverse=True)[:25]
    except Exception as e:
        print(f"  Comment fetch error: {e}")
        return []


# ---------------------------------------------------------------------------
# Text normalization & fuzzy matching
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_likely_review(title: str, body: str) -> bool:
    """Coarse pre-filter: skip obvious non-review posts."""
    if len(body.strip()) < 40:
        return False
    return not _NON_REVIEW_RE.search(title)


def _fuzzy_match_shoes(text: str, title: str, shoes: list[dict]) -> list[dict]:
    """
    Return all shoes that fuzzy-match the text+title, with match scores.
    Uses a slightly looser threshold (82) here because Claude verifies downstream.
    """
    combined = _normalize(title + " " + text)
    matches = []
    for shoe in shoes:
        model_norm = _normalize(shoe["model"])
        brand_model_norm = _normalize(f"{shoe['brand']} {shoe['model']}")

        score = max(
            fuzz.token_set_ratio(model_norm, combined),
            fuzz.token_set_ratio(brand_model_norm, combined),
            fuzz.partial_ratio(model_norm, combined),
        )

        if score >= 82:
            matches.append({**shoe, "_match_score": score})

    # Sort best-match first (Claude will re-verify)
    return sorted(matches, key=lambda s: s["_match_score"], reverse=True)


# ---------------------------------------------------------------------------
# Claude: verify + extract in a single call
# ---------------------------------------------------------------------------

_CLAUDE_AVAILABLE = bool(os.getenv("ANTHROPIC_API_KEY"))

_PROCESS_PROMPT = """\
You are analyzing a Reddit post or comment to determine if it contains a genuine \
first-hand review of the {shoe_model}.

Text:
\"\"\"
{text}
\"\"\"

Answer in valid JSON only (no extra text):
{{
  "is_review": true/false,
  "summary": "1-2 sentence plain-English summary of the person's experience (empty string if not a review)",
  "pros": ["specific strength 1", "specific strength 2"],
  "cons": ["specific weakness 1", "specific weakness 2"]
}}

Rules:
- is_review = true only if the person has personally used/tested the {shoe_model}
- is_review = false for questions, comparisons without ownership, off-topic posts
- pros/cons must be SPECIFIC to this shoe (3-9 words each, max 5 each)
- Do NOT include generic filler like "good shoe" or "I liked it"
- If is_review is false, set pros/cons to empty arrays and summary to ""
"""


def _process_with_claude(text: str, shoe_model: str) -> dict:
    """
    Single Claude call that verifies the review and extracts structured data.
    Returns {"is_review": bool, "summary": str, "pros": [...], "cons": [...]}.
    Falls back to keyword extraction on any error.
    """
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        prompt = _PROCESS_PROMPT.format(
            shoe_model=shoe_model,
            text=text[:2000],  # stay within token budget
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        result, _ = json.JSONDecoder().raw_decode(raw)
        return {
            "is_review": bool(result.get("is_review", False)),
            "summary": str(result.get("summary", ""))[:500],
            "pros": [str(p) for p in result.get("pros", [])[:5]],
            "cons": [str(c) for c in result.get("cons", [])[:5]],
        }
    except Exception as e:
        print(f"  Claude processing failed ({shoe_model}): {e} — using keyword fallback")
        return _keyword_fallback(text)


def _keyword_fallback(text: str) -> dict:
    """Simple keyword-based extraction used when Claude is unavailable."""
    from sentiment_analyzer import extract_pros_cons_keywords
    from review_summarizer import generate_summary_simple
    pc = extract_pros_cons_keywords(text)
    return {
        "is_review": True,   # assume it's a review (already fuzzy-matched)
        "summary": generate_summary_simple(text),
        "pros": pc.get("pros", []),
        "cons": pc.get("cons", []),
    }


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def match_and_process_posts(
    posts: list[dict],
    shoes: list[dict],
    include_comments: bool = True,
) -> list[dict]:
    """
    For every post (and optionally its comments):
      1. Fuzzy-match to candidate shoes
      2. Claude verifies + extracts data
      3. Return confirmed reviews ready for storage
    """
    confirmed: list[dict] = []
    seen_urls: set[str] = set()

    for post in posts:
        body = post["selftext"]
        title = post["title"]
        post_url = post["url"]

        # ------------------------------------------------------------------
        # Post body
        # ------------------------------------------------------------------
        candidate_shoes = _fuzzy_match_shoes(body, title, shoes)
        for shoe in candidate_shoes:
            if post_url in seen_urls:
                break
            if not _is_likely_review(title, body):
                break

            result = _process_with_claude(f"{title}\n\n{body}", shoe["model"])
            if result["is_review"]:
                confirmed.append({
                    "shoe_model": shoe["model"],
                    "shoe_brand": shoe["brand"],
                    "post_title": title,
                    "post_text": body,
                    "post_url": post_url,
                    "post_score": post["score"],
                    "post_created_utc": post["created_utc"],
                    "summary": result["summary"],
                    "pros": result["pros"],
                    "cons": result["cons"],
                })
                seen_urls.add(post_url)

        # ------------------------------------------------------------------
        # Comments
        # ------------------------------------------------------------------
        if include_comments:
            print(f"  Fetching comments: {title[:55]}…")
            comments = fetch_comments(post["permalink"])
            for comment in comments:
                cbody = comment["body"]
                curl = comment["permalink"]
                if curl in seen_urls or len(cbody.strip()) < 60:
                    continue

                candidate_shoes = _fuzzy_match_shoes(cbody, title, shoes)
                for shoe in candidate_shoes:
                    result = _process_with_claude(
                        f"Post title: {title}\n\nComment:\n{cbody}",
                        shoe["model"],
                    )
                    if result["is_review"]:
                        confirmed.append({
                            "shoe_model": shoe["model"],
                            "shoe_brand": shoe["brand"],
                            "post_title": f"Comment on: {title}",
                            "post_text": cbody,
                            "post_url": curl,
                            "post_score": comment["score"],
                            "post_created_utc": comment["created_utc"],
                            "summary": result["summary"],
                            "pros": result["pros"],
                            "cons": result["cons"],
                        })
                        seen_urls.add(curl)
                        break  # one shoe per comment URL

            time.sleep(0.6)  # rate limiting

    return confirmed


def store_reviews_in_db(reviews: list[dict], db) -> int:
    collection = db["reviews"]
    shoes_collection = db["shoes"]
    stored_count = 0

    for review in reviews:
        shoe_model = review["shoe_model"]
        shoe_brand = review["shoe_brand"]

        # Skip if this exact URL is already stored for this shoe
        if collection.find_one({
            "shoe_model": shoe_model,
            "reviews.post_url": review["post_url"],
        }):
            continue

        new_review = {
            "post_title":      review["post_title"],
            "post_text":       review["post_text"],
            "post_url":        review["post_url"],
            "post_score":      review["post_score"],
            "post_created_utc": review["post_created_utc"],
            "summary":         review["summary"],
            "pros":            review["pros"],
            "cons":            review["cons"],
        }

        collection.update_one(
            {"shoe_model": shoe_model, "shoe_brand": shoe_brand},
            {
                "$setOnInsert": {"shoe_model": shoe_model, "shoe_brand": shoe_brand},
                "$addToSet":    {"reviews": new_review},
            },
            upsert=True,
        )
        # Invalidate embedding so it regenerates with new review content
        shoes_collection.update_one(
            {"model": shoe_model},
            {"$set": {"embeddings": None}},
        )
        stored_count += 1

    return stored_count


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def scrape_and_store_reviews(limit: int = 100, include_comments: bool = True) -> int:
    uri = os.getenv("MONGO_URI")
    client = MongoClient(uri, server_api=ServerApi("1"))
    db = client["shoe_scout"]

    shoes = list(db["shoes"].find({}, {"_id": 0, "model": 1, "brand": 1}))
    print(f"Loaded {len(shoes)} shoes from DB")

    print("Fetching posts…")
    posts = fetch_all_posts(limit=limit)
    print(f"Total unique posts: {len(posts)}")

    print("Matching & processing with Claude…")
    reviews = match_and_process_posts(posts, shoes, include_comments=include_comments)
    print(f"Confirmed reviews: {len(reviews)}")

    stored = store_reviews_in_db(reviews, db)
    print(f"Stored {stored} new reviews in DB")
    return stored


def get_shoes_from_db():
    uri = os.getenv("MONGO_URI")
    client = MongoClient(uri, server_api=ServerApi("1"))
    return list(client["shoe_scout"]["shoes"].find({}, {"_id": 0, "model": 1, "brand": 1}))


if __name__ == "__main__":
    stored = scrape_and_store_reviews(limit=100, include_comments=True)
    print(f"\nDone — {stored} new reviews stored.")
