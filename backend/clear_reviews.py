#!/usr/bin/env python3
"""Script to clear all reviews from the database"""
import os
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv

load_dotenv()

def clear_all_reviews():
    uri = os.getenv("MONGO_URI")
    client = MongoClient(uri, server_api=ServerApi('1'))
    db = client["shoe_scout"]
    reviews_collection = db["reviews"]
    
    result = reviews_collection.delete_many({})
    print(f"Cleared {result.deleted_count} review documents from the database")
    return result.deleted_count

if __name__ == "__main__":
    clear_all_reviews()
