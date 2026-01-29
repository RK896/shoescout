# 👟 ShoeScout

**ShoeScout** is a full-stack running shoe deal aggregator that helps users find the best prices and community reviews. It combines retailer scraping, Reddit review insights, and semantic search so users can compare shoes and discover options by intent (e.g. "comfortable daily trainer").

## 📽️ Demo

![Project Demo](assets/demo.gif)

## Features

- **Search & Compare** — Find shoes by brand or model and compare prices across retailers (New Balance, Running Warehouse, Nike).
- **Semantic Search** — Search by intent using SBERT (Sentence Transformers). Embeddings include Reddit review text for better relevance (e.g. "lightweight", "daily trainer").
- **Reddit Review Insights** — Ingest posts and comments from r/RunningShoeGeeks; fuzzy-match to shoes; show summaries, pros/cons, and links to Reddit.
- **Up-to-date Data** — Retailer scraping and Reddit ingestion run on a schedule (e.g. GitHub Actions) so prices and reviews stay current.

## 🛠 Tech Stack

| Layer        | Tech |
|-------------|------|
| **Backend** | Python, FastAPI, MongoDB |
| **Frontend**| React, Vite |
| **Scraping**| Selenium (retailers), Requests (Reddit JSON API) |
| **ML / NLP**| Sentence Transformers (SBERT), Hugging Face Inference (summarization), keyword-based pros/cons |
| **Deploy**  | Render (backend), GitHub Pages (frontend), GitHub Actions (scraping, deploy, ping) |

## Environment Variables

### Local / Backend (`.env` in `backend/`)

| Variable | Required | Description |
|----------|----------|-------------|
| `MONGO_URI` | Yes | MongoDB connection string (e.g. Atlas). |
| `HUGGINGFACE_API_KEY` or `HF_TOKEN` | No | Hugging Face token for summarization (higher rate limits). Without it, summarization falls back to a simple extractive method. |

### Frontend (production build)

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_API_URL` | Yes (prod) | Backend API URL (e.g. `https://shoescout.onrender.com`). Set when building for production so the frontend calls the right API. |

### Render (backend)

- **MONGO_URI** — Required. Set in Render dashboard → Service → Environment.
- **HUGGINGFACE_API_KEY** (or **HF_TOKEN**) — Optional. Set if you want LLM summarization in production.

### GitHub

- **Secrets used by workflows**
  - **MONGO_URI** — Used by the scraping workflow to write to MongoDB.
  - **GH_TOKEN** — Used by the deploy workflow to push to `gh-pages`.
  - **VITE_API_URL** — Set when building the frontend (e.g. `https://shoescout.onrender.com`) so the deployed site calls your Render backend. Add as a repo secret and use it in the deploy workflow build step.
- **Optional:** **HUGGINGFACE_API_KEY** — If you add Reddit scraping to the automation, set this so summaries use the Hugging Face API in CI.

## Setup (local)

1. **Backend**
   ```bash
   cd backend
   pip install -r requirements.txt
   cp .env.example .env   # add MONGO_URI (and optional HF token)
   uvicorn main:app --reload
   ```
2. **Frontend**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   Default API URL is `http://localhost:8000`. Override with `VITE_API_URL` if needed.

3. **Scraping (optional)**  
   Retailer scrape: `python backend/scrape_runner.py`  
   Reddit reviews: `POST /scrape_reviews` on the running API, or call `scrape_and_store_reviews()` from `scraper.reddit_scraper`.

## To Do

- Add more retailer scrapers (e.g. Adidas, Zappos).
- Add sorting and filtering (e.g. by price, brand).
- Optional: Docker for one-command local run.
