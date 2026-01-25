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

def generate_embeddings(shoe_dict):
    if not EMBEDDINGS_AVAILABLE:
        raise ImportError("sentence-transformers not available. Please upgrade the package.")
    embedding = model.encode(create_shoe_text(shoe_dict))
    # Convert numpy array to list for JSON serialization
    return embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)

def generate_embeddings_batch(shoe_dicts):
    """Generate embeddings for multiple shoes at once (much faster)"""
    if not EMBEDDINGS_AVAILABLE:
        raise ImportError("sentence-transformers not available. Please upgrade the package.")
    texts = [create_shoe_text(shoe) for shoe in shoe_dicts]
    embeddings = model.encode(texts, show_progress_bar=False)
    # Convert 2D numpy array to list of lists for JSON serialization
    # embeddings is shape (n_shoes, embedding_dim)
    return [emb.tolist() for emb in embeddings]


def create_shoe_text(shoe_dict):
    text = f"{shoe_dict['brand']} {shoe_dict['model']} running shoe"
    retailers = shoe_dict.get('retailers', [])
    if retailers:
        retailer_info = []
        for r in retailers:
            retailer_info.append(f"{r['retailer']} for {r['price']}")
        text += " available at " + ", ".join(retailer_info)
    return text