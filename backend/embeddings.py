import os
from dotenv import load_dotenv
load_dotenv()

# Skip loading the model when DISABLE_EMBEDDINGS=1 (e.g. Render 512MB to avoid OOM).
# Search still works by encoding the query via Hugging Face Inference API (remote).
DISABLE_EMBEDDINGS = os.getenv("DISABLE_EMBEDDINGS", "").strip().lower() in ("1", "true", "yes")

# Same model ID for local and HF API so embeddings are compatible (384 dims).
EMBEDDING_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"

model = None
EMBEDDINGS_AVAILABLE = False

if not DISABLE_EMBEDDINGS:
    try:
        from sentence_transformers import SentenceTransformer
        try:
            model = SentenceTransformer(EMBEDDING_MODEL_ID)
            EMBEDDINGS_AVAILABLE = True
        except Exception as e:
            print(f"Warning: Failed to initialize sentence-transformers model: {e}")
            model = None
    except (ImportError, Exception) as e:
        print(f"Warning: sentence-transformers not available: {e}")
        model = None
else:
    print("Embeddings: model disabled (DISABLE_EMBEDDINGS=1). Search will use Hugging Face Inference API for queries.")

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


def encode_query_via_api(query: str):
    """Encode a search query using Hugging Face Inference API (no local model).
    Use when DISABLE_EMBEDDINGS=1 on Render so semantic search still works.
    Returns list of floats (384 dims) or None on failure.
    """
    if not query or not query.strip():
        return None
    try:
        from huggingface_hub import InferenceClient  # type: ignore
        token = os.getenv("HUGGINGFACE_API_KEY") or os.getenv("HF_TOKEN")
        if not token:
            return None
        client = InferenceClient(provider="hf-inference", api_key=token, timeout=15.0)
        # Truncate to avoid token limit
        text = query.strip()[:512]
        result = client.feature_extraction(text, model=EMBEDDING_MODEL_ID)
        if result is None:
            return None
        # HF returns list of lists for feature_extraction (one embedding = result[0])
        if isinstance(result, list) and result:
            emb = result[0] if isinstance(result[0], list) else result
            return list(emb) if isinstance(emb, (list, tuple)) else None
        return None
    except Exception as e:
        print(f"Remote query encoding failed: {e}")
        return None