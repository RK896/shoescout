import requests
import json

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
            if shoe_model in post_text:
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



if __name__ == "__main__":
    posts = scrape_runningshoegeeks(limit=5)
    print(f"Found {len(posts)} posts")
    if posts:
        print(f"First post: {posts[0]['title']}")
