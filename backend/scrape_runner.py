from main import scrape_and_store

if __name__ == "__main__":
    scrape_and_store()
    # Reddit review ingestion (posts + comments, summaries + pros/cons)
    from scraper.reddit_scraper import scrape_and_store_reviews
    stored = scrape_and_store_reviews(limit=100, include_comments=True)
    print(f"Reddit: stored {stored} new reviews")