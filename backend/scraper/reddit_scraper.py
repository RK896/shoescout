from typing import Any
from pymongo import MongoClient
from dotenv import load_dotenv
from pymongo.server_api import ServerApi
import os
import requests
import json
from rapidfuzz import fuzz
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from review_summarizer import generate_summary

load_dotenv()

def scrape_runningshoegeeks(limit=100):
    url = "https://www.reddit.com/r/RunningShoeGeeks/hot.json"
    params = {"limit": limit}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(url, params=params, headers=headers)
    if response.status_code == 200:
        try:
            data = response.json()
            posts = []
            for post in data['data']['children']:
                try:
                    post_data = post['data']
                    title = post_data['title']
                    selftext = post_data['selftext']
                    link_url = post_data['url']
                    created_utc = post_data['created_utc']
                    score = post_data['score']
                    permalink = post_data['permalink']
                    posts.append({
                        'title': title,
                        'selftext': selftext,
                        'link_url': link_url,
                        'created_utc': created_utc,
                        'score': score,
                        'permalink': f'https://www.reddit.com{permalink}'
                    })
                except Exception as e:
                    print(f"Error processing post: {e}")
                    continue
            return posts
        except Exception as e:
            print(f"Error parsing Reddit response: {e}")
            return []
    else:
        return []

def match_posts_to_shoes(posts, shoes):
    matched_reviews = []

    # loop thorugh each post and check if any shoe model appears in title or selftext
    # add to matched_reviews if match found
    for post in posts:
        post_text = f"{post['title']} {post['selftext']}".lower()
        for shoe in shoes:
            shoe_model = shoe['model'].lower()
            shoe_brand = shoe['brand'].lower()
            # Use partial_ratio to check if shoe model appears anywhere in post text
            # partial_ratio is better for substring matching (model in long post text)
            model_match = fuzz.partial_ratio(shoe_model, post_text)
            brand_model_match = fuzz.partial_ratio(f"{shoe_brand} {shoe_model}", post_text)
            
            # Match if similarity is above 70% (adjust threshold as needed)
            if model_match > 90 or brand_model_match > 90:
                matched_reviews.append({
                    'shoe_model': shoe['model'],
                    'shoe_brand': shoe['brand'],
                    'post_title': post['title'],
                    'post_text': post['selftext'],
                    'post_url': post['permalink'],
                    'post_score': post['score'],
                    'post_created_utc': post['created_utc']
                })
    return matched_reviews

def store_reviews_in_db(reviews, db):
    collection = db['reviews']
    stored_count = 0

    for review in reviews:
        shoe_model = review['shoe_model']
        shoe_brand = review['shoe_brand']
        
        # Generate summary when storing the review
        post_text = review.get('post_text', '')
        summary = generate_summary(post_text)
        
        new_review = {
            "post_title": review['post_title'],
            "post_text": review['post_text'],
            "post_url": review['post_url'],
            "post_score": review['post_score'],
            "post_created_utc": review['post_created_utc'],
            "summary": summary  # Store the summary
        }

        # Check if this exact review already exists (by post_url)
        existing_doc = collection.find_one({
            "shoe_model": shoe_model,
            "shoe_brand": shoe_brand,
            "reviews.post_url": review['post_url']
        })
        
        if existing_doc:
            continue  # Skip duplicate
        
        # Add review to existing shoe or create new document
        collection.update_one(
            {"shoe_model": shoe_model, "shoe_brand": shoe_brand},
            {
                "$setOnInsert": {
                    "shoe_model": shoe_model,
                    "shoe_brand": shoe_brand
                },
                "$addToSet": {"reviews": new_review}  # Add review if not already present
            },
            upsert=True
        )
        stored_count += 1
    
    return stored_count


def scrape_and_store_reviews(limit=100):
    uri = os.getenv("MONGO_URI")
    client = MongoClient(uri, server_api=ServerApi('1'))
    db = client["shoe_scout"]
    shoes = get_shoes_from_db()
    posts = scrape_runningshoegeeks(limit=limit)
    reviews = match_posts_to_shoes(posts, shoes)
    stored_count = store_reviews_in_db(reviews, db)
    return stored_count

def print_reviews():
    uri = os.getenv("MONGO_URI")
    client = MongoClient(uri, server_api=ServerApi('1'))
    db = client["shoe_scout"]
    collection = db["reviews"]
    reviews = list(collection.find({}, {"_id": 0, "shoe_model": 1, "shoe_brand": 1, "reviews": 1}))
    for review in reviews:
        print(review)

def get_shoes_from_db():
    uri = os.getenv("MONGO_URI")
    client = MongoClient(uri, server_api=ServerApi('1'))
    db = client["shoe_scout"]
    collection = db["shoes"]

    shoes = list(collection.find({}, {"_id": 0, "model": 1, "brand": 1}))
    return shoes

if __name__ == "__main__":
    stored = scrape_and_store_reviews(limit=10)
    print(f"Stored {stored} new reviews")
    print_reviews()
