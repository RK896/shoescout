try:
    from sentence_transformers import SentenceTransformer
    try:
        model = SentenceTransformer("all-MiniLM-L6-v2")
        EMBEDDINGS_AVAILABLE = True
    except Exception as e:
        print(f"Warning: Failed to initialize sentence-transformers model: {e}")
        print("Please upgrade: pip install --upgrade sentence-transformers")
        model = None
        EMBEDDINGS_AVAILABLE = False
except (ImportError, Exception) as e:
    print(f"Warning: sentence-transformers not available: {e}")
    print("Please upgrade: pip install --upgrade sentence-transformers")
    model = None
    EMBEDDINGS_AVAILABLE = False

# Max characters for embedding text (model has ~512 token limit, ~2000 chars safe)
MAX_EMBEDDING_TEXT_LEN = 2000

def create_shoe_text(shoe_dict, review_text=None):
    """Create text for embedding: base shoe info + optional Reddit review content."""
    text = f"{shoe_dict.get('brand', '')} {shoe_dict.get('model', '')} running shoe"
    retailers = shoe_dict.get('retailers', [])
    if retailers:
        retailer_info = []
        for r in retailers:
            retailer_info.append(f"{r['retailer']} for {r['price']}")
        text += " available at " + ", ".join(retailer_info)
    
    # Include Reddit review data so semantic search matches "comfortable", "daily trainer", etc.
    if review_text and review_text.strip():
        text += " " + review_text.strip()
    
    # Truncate to avoid exceeding model token limit
    if len(text) > MAX_EMBEDDING_TEXT_LEN:
        text = text[:MAX_EMBEDDING_TEXT_LEN - 3] + "..."
    return text

def generate_embeddings(shoe_dict, review_text=None):
    if not EMBEDDINGS_AVAILABLE:
        raise ImportError("sentence-transformers not available. Please upgrade the package.")
    embedding = model.encode(create_shoe_text(shoe_dict, review_text=review_text))
    # Convert numpy array to list for JSON serialization
    return embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)

def generate_embeddings_batch(shoe_dicts, reviews_by_model=None):
    """Generate embeddings for multiple shoes at once (much faster).
    reviews_by_model: optional dict mapping shoe model -> string of review content to include.
    """
    if not EMBEDDINGS_AVAILABLE:
        raise ImportError("sentence-transformers not available. Please upgrade the package.")
    if reviews_by_model is None:
        reviews_by_model = {}
    texts = [
        create_shoe_text(shoe, review_text=reviews_by_model.get(shoe.get("model"), ""))
        for shoe in shoe_dicts
    ]
    embeddings = model.encode(texts, show_progress_bar=False)
    # Convert 2D numpy array to list of lists for JSON serialization
    return [emb.tolist() for emb in embeddings]