"""Run Reddit review scraping only (posts + comments, summaries + pros/cons)."""
from scraper.reddit_scraper import scrape_and_store_reviews

if __name__ == "__main__":
    stored = scrape_and_store_reviews(limit=100, include_comments=True)
    print(f"Reddit: stored {stored} new reviews")
