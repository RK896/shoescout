from sentence_transformers import SentenceTransformer
model = SentenceTransformer("all-MiniLM-L6-v2")

def generate_embeddings(shoe_dict):
    return model.encode(create_shoe_text(shoe_dict))


def create_shoe_text(shoe_dict):
    text = f"{shoe_dict['brand']} {shoe_dict['model']} running shoe"
    retailers = shoe_dict.get('retailers', [])
    if retailers:
        retailer_info = []
        for r in retailers:
            retailer_info.append(f"{r['retailer']} for {r['price']}")
        text += " available at " + ", ".join(retailer_info)
    return text