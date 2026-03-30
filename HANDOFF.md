# ShoeScout Handoff Documentation

A full-stack running shoe deal aggregator with AI-powered recommendations. Scrapes prices from 11 retailers, pulls community reviews from Reddit, and uses Claude AI for personalized shoe recommendations.

**Live at:** GitHub Pages (frontend) + Render (backend) + MongoDB Atlas

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture Overview](#architecture-overview)
3. [Technology Stack](#technology-stack)
4. [API Endpoints](#api-endpoints)
5. [Scraper System](#scraper-system)
6. [AI Integrations](#ai-integrations)
7. [Database Schema](#database-schema)
8. [CI/CD & Deployment](#cicd--deployment)
9. [Environment Variables](#environment-variables)
10. [Recent Changes](#recent-changes)
11. [Future Roadmap](#future-roadmap)

---

## Quick Start

### Local Development

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend
cd frontend
npm install && npm run dev
```

### Required Environment Variables

```bash
MONGO_URI=mongodb+srv://...
ANTHROPIC_API_KEY=sk-ant-...
COHERE_API_KEY=...
ADMIN_KEY=<any-random-string>
HF_TOKEN=hf_...  # Optional fallback
```

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        GitHub Actions                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ scraper.yaml │  │reddit_scraper│  │  deploy.yaml │          │
│  │  (every 6h)  │  │  (weekly)    │  │ (on push)    │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                 │                  │                  │
│         ▼                 ▼                  ▼                  │
│  scrape_runner.py  reddit_scraper.py   npm run build            │
│  (11 scrapers)     (Reddit + Claude)   (Vite → dist/)          │
└─────────┬─────────────────┬──────────────────┬──────────────────┘
          │                 │                  │
          ▼                 ▼                  ▼
   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
   │ MongoDB Atlas │  │ MongoDB Atlas │  │ GitHub Pages │
   │   shoes       │  │   reviews     │  │  (frontend)  │
   └──────┬────────┘  └──────┬────────┘  └──────┬───────┘
          │                  │                   │
          └────────┬─────────┘                   │
                   ▼                             │
          ┌────────────────┐                     │
          │  FastAPI       │◄────────────────────┘
          │  (Render)      │        API calls
          │  + Claude AI   │
          │  + Cohere      │
          └────────────────┘
```

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | React 19, Vite 6.3 | UI framework and build tool |
| **Backend** | FastAPI 0.115, Python 3.12 | REST API server |
| **Server** | Gunicorn + Uvicorn | Production WSGI/ASGI server |
| **Database** | MongoDB Atlas | Document store |
| **Scraping** | Requests + BeautifulSoup / Selenium | Web scraping |
| **Embeddings** | Cohere API (`embed-english-light-v3.0`) | 384-dim semantic vectors |
| **AI Chat** | Claude Haiku | Chatbot, summaries, pros/cons |
| **Fuzzy Matching** | RapidFuzz | Reddit post → shoe matching |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check |
| `GET` | `/health` | Detailed status (DB, embeddings) |
| `GET` | `/shoes` | Paginated shoe catalog |
| `GET` | `/search?q=` | Semantic search (Cohere embeddings) |
| `GET` | `/brands` | List all brands with counts |
| `GET` | `/reviews?shoe_model=` | Get reviews for a shoe |
| `GET` | `/shoes/{model}/price-history` | Historical prices |
| `GET` | `/shoes/{model}/similar` | Similar shoes by embedding |
| `GET` | `/deals` | Shoes discounted vs historical avg |
| `POST` | `/scrape` | Trigger all retailer scrapers |
| `POST` | `/scrape_reviews` | Trigger Reddit scraper |
| `POST` | `/chat` | AI chatbot endpoint |
| `DELETE` | `/reviews` | Clear reviews (requires `X-Admin-Key`) |

---

## Scraper System

### Overview

All scrapers are **API-based** (no Selenium) for speed and reliability. Common patterns:

1. **JSON in script tags** - Product data in `<script type="application/ld+json">`
2. **HTML data attributes** - GTM/product data in `data-*` attributes
3. **REST API endpoints** - Internal APIs returning JSON

### Scrapers Summary

| Retailer | File | Method | Products | Time |
|----------|------|--------|----------|------|
| Running Warehouse | `runningwarehouse_api.py` | HTML data attributes | ~200 | ~2s |
| Dick's Sporting Goods | `dicks.py` | REST API | ~600 | ~30s |
| Zappos | `zappos_api.py` | REST API | ~100 | ~15s |
| Holabird Sports | `holabird.py` | Third-party search API | ~300 | ~45s |
| Saucony | `saucony_api.py` | JSON-LD | ~50 | ~5s |
| Brooks | `brooks.py` | SFCC API | ~100 | ~10s |
| Fleet Feet | `fleetfeet.py` | JSON script tags | ~900 | ~45s |
| Nike | `nike.py` | CSS selectors | varies | varies |
| New Balance | `newbalance.py` | SFCC BEM classes | varies | varies |
| HOKA | `hoka.py` | Product tiles | varies | varies |
| Adidas | `adidas.py` | data-auto-id attrs | varies | varies |

### Scraper Details

#### Running Warehouse (`runningwarehouse_api.py`)

**15x faster than old Selenium scraper.** Uses GTM data attributes:

```python
# Data in HTML attributes
<div class="cattable-wrap-cell gtm_impression"
     data-gtm_impression_brand="Brooks"
     data-gtm_impression_name="Brooks Adrenaline GTS 25"
     data-gtm_impression_price="154.95">
```

**URLs:**
- Men's: `runningwarehouse.com/Mens_Road_Running_Shoes/catpage-MBESTUSE.html`
- Women's: `runningwarehouse.com/Womens_Road_Running_Shoes/catpage-WBESTUSE.html`

#### Dick's Sporting Goods (`dicks.py`)

**REST API with full catalog browsing:**

```
GET https://prod-catalog-product-api.dickssportinggoods.com/v2/search?searchVO={JSON}
```

Required headers: `channel: dsg`, `x-dsg-platform: v2`

Returns product + pricing data. Team edition shoes (NFL/NCAA) are filtered out.

#### Zappos (`zappos_api.py`)

**Automatic session management:**

```
GET https://www.zappos.com/directapi/janus/recos/get?filter=...&txt=...
```

Session cookies obtained automatically by visiting the site first.

#### Holabird Sports (`holabird.py`)

**Third-party SearchServerAPI:**

```
GET https://searchserverapi.com/getresults?api_key=1T0U8M9s3R&q=...
```

Includes detailed variant info (sizes, widths, availability).

#### Saucony (`saucony_api.py`)

**JSON-LD structured data:**

```python
# All products in <script type="application/ld+json">
{
  "@type": "ItemList",
  "itemListElement": [{ "@type": "Product", "name": "Endorphin Speed 5", ... }]
}
```

Single request gets all products per category.

#### Brooks (`brooks.py`)

**SFCC Search-UpdateGrid API:**

```
GET https://www.brooksrunning.com/on/demandware.store/.../Search-UpdateGrid?cgid=mens-shoes
```

Requires session cookies. Initialize by visiting the site first.

#### Fleet Feet (`fleetfeet.py`)

**JSON in custom script tags:**

```python
soup.find_all("script", {"type": "application/json", "chuck-replace": "product-tile_inner"})
```

### Common Deduplication Pattern

All scrapers deduplicate by model name, keeping lowest price:

```python
for product in products:
    key = product.model.lower()
    if key not in seen or product.price < seen[key].price:
        seen[key] = product
```

### Reddit Scraper (`reddit_scraper.py`)

Scrapes r/RunningShoeGeeks and r/running:

1. **Fuzzy matching** with RapidFuzz (`token_set_ratio >= 85`)
2. **Claude verification** confirms genuine first-hand reviews
3. **Extracts pros/cons** via AI

Filters: score < 3 skipped, comments < 50 chars skipped, buy/sell posts excluded.

---

## AI Integrations

### 3-Tier Fallback System

| Feature | Tier 1 (Claude) | Tier 2 (HF) | Tier 3 (Always) |
|---------|-----------------|-------------|-----------------|
| Chatbot | Claude Haiku | — | Text search |
| Summary | Claude | Mistral-7B | First sentence |
| Pros/Cons | Claude JSON | Mistral-7B | Keyword matching |
| Verification | Claude | — | Accept all |
| Search | — | Cohere | Text/regex |

### Chatbot Flow

1. User sends message ("marathon shoe under $150")
2. Backend finds 8 relevant shoes via semantic search
3. Fetches top 3 reviews per shoe
4. Claude receives shoe data + reviews + user question
5. Returns specific recommendation with prices and community feedback

### Key AI Files

- `chat.py` — Claude chatbot logic
- `embeddings.py` — Cohere API wrapper
- `review_summarizer.py` — 3-tier summary generation
- `sentiment_analyzer.py` — 3-tier pros/cons extraction

---

## Database Schema

### `shoes` Collection

```json
{
  "model": "Nike Pegasus 41",
  "brand": "Nike",
  "image": "https://...",
  "retailers": [
    { "retailer": "Nike", "price": "$129.99", "link": "https://..." }
  ],
  "price_history": [
    { "retailer": "Nike", "price": "$129.99", "price_value": 129.99, "timestamp": "..." }
  ],
  "embeddings": [0.123, 0.456, ...]
}
```

### `reviews` Collection

```json
{
  "shoe_model": "Nike Pegasus 41",
  "shoe_brand": "Nike",
  "reviews": [
    {
      "post_title": "Pegasus 41 after 100 miles",
      "post_text": "...",
      "post_url": "https://reddit.com/...",
      "post_score": 42,
      "summary": "Great daily trainer with responsive cushioning.",
      "pros": ["responsive cushioning", "durable outsole"],
      "cons": ["sizing runs narrow"]
    }
  ]
}
```

---

## CI/CD & Deployment

### GitHub Actions Workflows

| Workflow | Schedule | Purpose |
|----------|----------|---------|
| `scraper.yaml` | Every 6 hours | Run all retailer scrapers |
| `reddit_scraper.yaml` | Weekly (Sunday) | Scrape Reddit reviews |
| `deploy.yaml` | On push to main | Build React → GitHub Pages |
| `ping_render.yaml` | Every 15 min | Keep Render warm |

### Deployment Targets

| Service | Platform | Notes |
|---------|----------|-------|
| Frontend | GitHub Pages | Auto-deploy via `gh-pages` branch |
| Backend | Render (Starter) | Gunicorn + Uvicorn |
| Database | MongoDB Atlas | Free/shared tier |

---

## Environment Variables

| Variable | Where | Purpose |
|----------|-------|---------|
| `MONGO_URI` | Backend, CI | MongoDB connection string |
| `ANTHROPIC_API_KEY` | Backend, CI | Claude API |
| `COHERE_API_KEY` | Backend, CI | Embeddings |
| `ADMIN_KEY` | Backend | Protects DELETE endpoint |
| `VITE_API_URL` | CI | Backend URL for frontend build |
| `HF_TOKEN` | Backend, CI | Hugging Face fallback |

---

## Recent Changes

### Scrapers

- **Migrated to API-based scrapers** — All major scrapers now use direct HTTP/API calls instead of Selenium. 10-100x faster, no browser dependencies.
- **New scrapers added:** Dick's, Zappos, Holabird, Saucony (API-based), updated Fleet Feet and Brooks
- **Running Warehouse rewritten** — From Selenium to HTML data attributes. 15x faster, 4x more products.

### Backend

- **Cohere embeddings** — Replaced local sentence-transformers with Cohere API (fits in Render's memory)
- **Fork-safe MongoDB** — Lazy-initialized connections for Gunicorn workers
- **Price parsing** — Robust regex-based parser handles edge cases
- **Secure DELETE** — Requires `X-Admin-Key` header

### Frontend

- **Debounced search** — 300ms wait after typing
- **Lazy review loading** — Reviews fetched on click, not page load
- **AI Chatbot** — Claude-powered recommendations
- **Visual redesign** — Clean navy/orange theme

### Reddit Scraper

- **Better fuzzy matching** — Two-tier approach with token_set_ratio
- **Claude verification** — Confirms genuine reviews, extracts pros/cons
- **Quality filters** — Score < 3 skipped, short comments filtered

---

## Future Roadmap

- [ ] Women's shoes (new scraper URLs)
- [ ] Docker setup for local dev
- [ ] Vector database (Pinecone/Weaviate) as scale grows
- [ ] Error monitoring (Sentry)
- [ ] Rate limiting on API
- [ ] User accounts and saved preferences
- [ ] Price drop alerts

---

## Code Metrics

| Metric | Value |
|--------|-------|
| Total Lines | ~6,500+ |
| API Endpoints | 15 |
| Scraper Modules | 12 |
| AI Integrations | 4 |
| GitHub Workflows | 4 |

---

## File Structure

```
shoescout/
├── backend/
│   ├── main.py              # FastAPI app, all endpoints
│   ├── chat.py              # Claude chatbot
│   ├── embeddings.py        # Cohere embeddings
│   ├── review_summarizer.py # AI summaries
│   ├── sentiment_analyzer.py# Pros/cons extraction
│   ├── scrape_runner.py     # Orchestrates all scrapers
│   └── scraper/
│       ├── runningwarehouse_api.py
│       ├── dicks.py
│       ├── zappos_api.py
│       ├── holabird.py
│       ├── saucony_api.py
│       ├── brooks.py
│       ├── fleetfeet.py
│       ├── nike.py
│       ├── newbalance.py
│       ├── hoka.py
│       ├── adidas.py
│       └── reddit_scraper.py
├── frontend/
│   ├── src/App.jsx          # Main React app
│   └── src/App.css          # Styles
└── .github/workflows/
    ├── scraper.yaml
    ├── reddit_scraper.yaml
    ├── deploy.yaml
    └── ping_render.yaml
```
