from copy import deepcopy

from fastapi.testclient import TestClient

import main


class FakeCursor(list):
    def skip(self, count):
        return FakeCursor(self[count:])

    def limit(self, count):
        return FakeCursor(self[:count])


class FakeCollection:
    def __init__(self, shoes):
        self._shoes = [deepcopy(shoe) for shoe in shoes]

    def _matches_query(self, shoe, query):
        for key, value in (query or {}).items():
            if key == "brand" and shoe.get("brand") != value:
                return False
            if key == "retailers.retailer":
                if not any(retailer.get("retailer") == value for retailer in shoe.get("retailers", [])):
                    return False
            if key == "category" and shoe.get("category") != value:
                return False
            if key == "gender":
                regex = value.get("$regex")
                options = value.get("$options", "")
                gender = shoe.get("gender", "")
                if regex and "i" in options:
                    if regex.lower().strip("^") not in gender.lower():
                        return False
                elif regex and regex not in gender:
                    return False
        return True

    def find(self, query=None, projection=None):
        return FakeCursor([deepcopy(shoe) for shoe in self._shoes if self._matches_query(shoe, query)])

    def count_documents(self, query=None):
        return len(self.find(query))

    def find_one(self, query=None, projection=None):
        results = self.find(query, projection)
        return results[0] if results else None


client = TestClient(main.app)


def test_get_shoes_filters_by_size_and_width(monkeypatch):
    shoes = [
        {
            "brand": "Brooks",
            "model": "Brooks Ghost 16",
            "price": "$95.00",
            "image": "ghost.jpg",
            "gender": "Men's",
            "category": "road",
            "retailers": [{"retailer": "Holabird Sports", "price": "$95.00", "link": "https://example.com/ghost"}],
            "size_variants": [
                {"size": "10.5", "width": "Wide", "available": True, "link": "https://example.com/ghost/10.5-wide"}
            ],
            "price_history": [
                {"retailer": "Holabird Sports", "price": "$100.00", "price_value": 100.0},
                {"retailer": "Holabird Sports", "price": "$100.00", "price_value": 100.0},
            ],
            "embeddings": [0.1, 0.2, 0.3],
        },
        {
            "brand": "Brooks",
            "model": "Brooks Ghost 16 Narrow",
            "price": "$93.00",
            "image": "ghost-narrow.jpg",
            "gender": "Men's",
            "category": "road",
            "retailers": [{"retailer": "Holabird Sports", "price": "$93.00", "link": "https://example.com/ghost-narrow"}],
            "size_variants": [
                {"size": "10.5", "width": "Narrow", "available": True, "link": "https://example.com/ghost/10.5-narrow"}
            ],
            "price_history": [
                {"retailer": "Holabird Sports", "price": "$100.00", "price_value": 100.0},
                {"retailer": "Holabird Sports", "price": "$100.00", "price_value": 100.0},
            ],
            "embeddings": [0.4, 0.5, 0.6],
        },
    ]
    monkeypatch.setattr(main, "get_collection", lambda: FakeCollection(shoes))

    response = client.get("/shoes", params={"size": "10.5", "width": "wide"})
    body = response.json()

    assert response.status_code == 200
    assert body["total"] == 1
    assert body["total_pages"] == 1
    assert len(body["shoes"]) == 1
    shoe = body["shoes"][0]
    assert shoe["model"] == "Brooks Ghost 16"
    assert shoe["available_sizes"] == ["10.5"]
    assert shoe["available_widths"] == ["Wide"]
    assert shoe["discount_pct"] == 5.0
    assert shoe["average_price"] == 100.0


def test_get_shoes_filters_by_min_discount(monkeypatch):
    shoes = [
        {
            "brand": "Nike",
            "model": "Nike Pegasus 41",
            "price": "$96.00",
            "image": "pegasus.jpg",
            "gender": "Men's",
            "category": "road",
            "retailers": [{"retailer": "Nike", "price": "$96.00", "link": "https://example.com/pegasus"}],
            "size_variants": [{"size": "10", "width": "Standard", "available": True, "link": "https://example.com/pegasus/10"}],
            "price_history": [
                {"retailer": "Nike", "price": "$100.00", "price_value": 100.0},
                {"retailer": "Nike", "price": "$100.00", "price_value": 100.0},
            ],
            "embeddings": [0.2, 0.3, 0.4],
        },
        {
            "brand": "Nike",
            "model": "Nike Vomero 18",
            "price": "$99.00",
            "image": "vomero.jpg",
            "gender": "Men's",
            "category": "road",
            "retailers": [{"retailer": "Nike", "price": "$99.00", "link": "https://example.com/vomero"}],
            "size_variants": [{"size": "10", "width": "Standard", "available": True, "link": "https://example.com/vomero/10"}],
            "price_history": [
                {"retailer": "Nike", "price": "$100.00", "price_value": 100.0},
                {"retailer": "Nike", "price": "$100.00", "price_value": 100.0},
            ],
            "embeddings": [0.5, 0.6, 0.7],
        },
    ]
    monkeypatch.setattr(main, "get_collection", lambda: FakeCollection(shoes))

    response = client.get("/shoes", params={"min_discount": 3})
    body = response.json()

    assert response.status_code == 200
    assert body["total"] == 1
    assert len(body["shoes"]) == 1
    shoe = body["shoes"][0]
    assert shoe["model"] == "Nike Pegasus 41"
    assert shoe["discount_pct"] == 4.0
    assert shoe["average_price"] == 100.0
