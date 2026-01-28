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
from sentiment_analyzer import extract_pros_cons

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

def scrape_comments_from_post(permalink):
    """Scrape top-level comments from a Reddit post"""
    # Reddit JSON API: append .json to permalink
    url = f"https://www.reddit.com{permalink}.json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            comments = []
            
            # Reddit returns [post_data, comment_data]
            if len(data) > 1 and 'data' in data[1]:
                comment_list = data[1]['data']['children']
                
                for item in comment_list:
                    if item['kind'] == 't1':  # t1 = comment
                        try:
                            comment_data = item['data']
                            # Skip deleted/removed comments
                            if comment_data.get('body') and comment_data['body'] not in ['[deleted]', '[removed]']:
                                # Only get top-level comments (replies can be very nested)
                                if comment_data.get('body'):
                                    # Build comment permalink
                                    comment_permalink = comment_data.get('permalink', '')
                                    if not comment_permalink.startswith('http'):
                                        comment_permalink = f"https://www.reddit.com{comment_permalink}"
                                    
                                    comments.append({
                                        'body': comment_data['body'],
                                        'score': comment_data.get('score', 0),
                                        'created_utc': comment_data.get('created_utc', 0),
                                        'permalink': comment_permalink
                                    })
                        except Exception as e:
                            print(f"Error processing comment: {e}")
                            continue
            
            return comments
    except Exception as e:
        print(f"Error scraping comments from {permalink}: {e}")
        return []
    
    return []

def match_text_to_shoes(text, shoes, source_title="", source_url=""):
    """Match text content (post or comment) to shoes"""
    matched_reviews = []
    text_lower = text.lower()
    
    for shoe in shoes:
        shoe_model = shoe['model'].lower()
        shoe_brand = shoe['brand'].lower()
        model_match = fuzz.partial_ratio(shoe_model, text_lower)
        brand_model_match = fuzz.partial_ratio(f"{shoe_brand} {shoe_model}", text_lower)
        
        if model_match > 90 or brand_model_match > 90:
            matched_reviews.append({
                'shoe_model': shoe['model'],
                'shoe_brand': shoe['brand'],
                'post_title': source_title,
                'post_text': text,
                'post_url': source_url,
                'post_score': 0,  # Comments don't have individual scores in our structure
                'post_created_utc': 0
            })
    
    return matched_reviews

def match_posts_to_shoes(posts, shoes, include_comments=False):
    matched_reviews = []

    # Loop through each post and check if any shoe model appears in title or selftext
    for post in posts:
        post_text = f"{post['title']} {post['selftext']}".lower()
        
        # Match post content
        post_matches = match_text_to_shoes(
            f"{post['title']} {post['selftext']}",
            shoes,
            source_title=post['title'],
            source_url=post['permalink']
        )
        
        for match in post_matches:
            match['post_score'] = post['score']
            match['post_created_utc'] = post['created_utc']
        matched_reviews.extend(post_matches)
        
        # If including comments, scrape and match comments
        if include_comments:
            print(f"Scraping comments from post: {post['title'][:50]}...")
            comments = scrape_comments_from_post(post['permalink'].replace('https://www.reddit.com', ''))
            
            # Limit to top 20 comments per post to avoid too many API calls
            for comment in comments[:20]:
                comment_text = comment['body']
                # Only process comments with meaningful length (at least 20 chars)
                if len(comment_text.strip()) < 20:
                    continue
                    
                # Match comment content
                comment_matches = match_text_to_shoes(
                    comment_text,
                    shoes,
                    source_title=f"Comment on: {post['title']}",
                    source_url=comment.get('permalink', post['permalink'])
                )
                
                for match in comment_matches:
                    match['post_text'] = comment_text  # Use comment body as post_text
                    match['post_score'] = comment.get('score', 0)
                    match['post_created_utc'] = comment.get('created_utc', 0)
                matched_reviews.extend(comment_matches)
            
            # Small delay to avoid rate limiting
            import time
            time.sleep(0.5)
    
    return matched_reviews

def store_reviews_in_db(reviews, db):
    collection = db['reviews']
    stored_count = 0

    for review in reviews:
        shoe_model = review['shoe_model']
        shoe_brand = review['shoe_brand']
        
        # Generate summary and extract pros/cons when storing the review
        post_text = review.get('post_text', '')
        summary = generate_summary(post_text)
        pros_cons = extract_pros_cons(post_text)
        
        new_review = {
            "post_title": review['post_title'],
            "post_text": review['post_text'],
            "post_url": review['post_url'],
            "post_score": review['post_score'],
            "post_created_utc": review['post_created_utc'],
            "summary": summary,  # Store the summary
            "pros": pros_cons.get("pros", []),  # Store pros
            "cons": pros_cons.get("cons", [])   # Store cons
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
        # Clear this shoe's embedding so it gets regenerated with new review content (semantic search)
        shoes_collection = db["shoes"]
        shoes_collection.update_one({"model": shoe_model}, {"$unset": {"embeddings": ""}})
        stored_count += 1
    
    return stored_count


def scrape_and_store_reviews(limit=100, include_comments=False):
    uri = os.getenv("MONGO_URI")
    client = MongoClient(uri, server_api=ServerApi('1'))
    db = client["shoe_scout"]
    shoes = get_shoes_from_db()
    posts = scrape_runningshoegeeks(limit=limit)
    reviews = match_posts_to_shoes(posts, shoes, include_comments=include_comments)
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
    stored = scrape_and_store_reviews(limit=100, include_comments=True)
    print(f"Stored {stored} new reviews")
    print_reviews()
