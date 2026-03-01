"""
Embedding generation for semantic shoe search via Cohere API.

Model: embed-english-light-v3.0 (384 dims, fast, free tier available)
- search_document input_type for indexing shoes
- search_query input_type for user search queries

Fallback: MongoDB text/regex search (no embeddings needed).
"""
import os
from dotenv import load_dotenv
load_dotenv()

COHERE_EMBEDDING_MODEL = "embed-english-light-v3.0"
EMBEDDINGS_AVAILABLE = False  # set to True once Cohere client confirmed at startup
MAX_EMBEDDING_TEXT_LEN = 2000

_cohere_client = None


def _init_cohere():
    global _cohere_client, EMBEDDINGS_AVAILABLE
    try:
        import cohere
        api_key = os.getenv("COHERE_API_KEY")
        if not api_key:
            print("Embeddings: COHERE_API_KEY not set — semantic search will use text fallback.")
            return
        _cohere_client = cohere.ClientV2(api_key=api_key)
        EMBEDDINGS_AVAILABLE = True
        print("Embeddings: Cohere client ready.")
    except ImportError:
        print("Embeddings: cohere package not installed. Run: pip install cohere")
    except Exception as e:
        print(f"Embeddings: Cohere init failed: {e}")


_init_cohere()


# ---------------------------------------------------------------------------
# Text preparation
# ---------------------------------------------------------------------------

def create_shoe_text(shoe_dict, review_text=None):
    """Build the text blob to embed for a shoe."""
    text = f"{shoe_dict.get('brand', '')} {shoe_dict.get('model', '')} running shoe"
    retailers = shoe_dict.get('retailers', [])
    if retailers:
        retailer_info = [f"{r['retailer']} for {r['price']}" for r in retailers]
        text += " available at " + ", ".join(retailer_info)
    if review_text and review_text.strip():
        text += " " + review_text.strip()
    if len(text) > MAX_EMBEDDING_TEXT_LEN:
        text = text[:MAX_EMBEDDING_TEXT_LEN - 3] + "..."
    return text


# ---------------------------------------------------------------------------
# Cohere API
# ---------------------------------------------------------------------------

def encode_query_via_api(query: str):
    """
    Encode a search query for semantic search.
    Returns list[float] (384 dims) or None on failure.
    """
    if not query or not query.strip():
        return None
    if not _cohere_client:
        return None
    try:
        response = _cohere_client.embed(
            texts=[query.strip()[:512]],
            model=COHERE_EMBEDDING_MODEL,
            input_type="search_query",
            embedding_types=["float"],
        )
        return list(response.embeddings.float_[0])
    except Exception as e:
        print(f"Cohere query encoding failed: {e}")
        return None


def encode_batch_via_api(texts: list, input_type: str = "search_document"):
    """
    Encode a batch of texts (shoe documents).
    Returns list[list[float]] or None on failure.
    Automatically batches in groups of 96 (Cohere max).
    """
    if not texts:
        return []
    if not _cohere_client:
        return None
    try:
        all_embeddings = []
        for i in range(0, len(texts), 96):
            batch = [t[:MAX_EMBEDDING_TEXT_LEN] for t in texts[i:i + 96]]
            response = _cohere_client.embed(
                texts=batch,
                model=COHERE_EMBEDDING_MODEL,
                input_type=input_type,
                embedding_types=["float"],
            )
            all_embeddings.extend([list(e) for e in response.embeddings.float_])
        return all_embeddings
    except Exception as e:
        print(f"Cohere batch encoding failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Kept for import compatibility — no-ops since we dropped local model
# ---------------------------------------------------------------------------

model = None  # no local model


def generate_embeddings(shoe_dict, review_text=None):
    raise ImportError("Local sentence-transformers removed. Use encode_batch_via_api instead.")


def generate_embeddings_batch(shoe_dicts, reviews_by_model=None):
    raise ImportError("Local sentence-transformers removed. Use encode_batch_via_api instead.")
