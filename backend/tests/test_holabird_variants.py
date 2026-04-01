from scraper.holabird import HolabirdProduct, ShoeVariant
from main import _shoe_matches_variant_filters


def test_holabird_product_to_dict_exports_variant_metadata():
    product = HolabirdProduct(
        brand="Nike",
        model="Nike Pegasus 41",
        price="$129.99",
        list_price="$149.99",
        image="https://example.com/shoe.jpg",
        link="https://example.com/product",
        gender="Men's",
        variants=[
            ShoeVariant(
                size="10",
                width="D",
                price=129.99,
                list_price=149.99,
                available=True,
                variant_id="variant-1",
                link="https://example.com/product?size=10",
            ),
            ShoeVariant(
                size="10.5",
                width="2E",
                price=129.99,
                list_price=149.99,
                available=False,
                variant_id="variant-2",
                link="https://example.com/product?size=10.5",
            ),
        ],
    )

    payload = product.to_dict()

    assert payload["gender"] == "Men's"
    assert payload["size_variants"][0]["size"] == "10"
    assert payload["size_variants"][0]["available"] is True
    assert payload["available_sizes"] == ["10"]
    assert payload["available_widths"] == ["D"]


def test_variant_filters_match_stored_size_variants():
    shoe = {
        "size_variants": [
            {"size": "10", "width": "D", "available": True},
            {"size": "10.5", "width": "2E", "available": True},
        ]
    }

    assert _shoe_matches_variant_filters(shoe, size="10")
    assert _shoe_matches_variant_filters(shoe, width="standard")
    assert _shoe_matches_variant_filters(shoe, size="10.5", width="wide")
    assert not _shoe_matches_variant_filters(shoe, size="11")
    assert not _shoe_matches_variant_filters(shoe, width="narrow")


def test_variant_filters_fall_back_to_available_size_and_width_lists():
    shoe = {
        "available_sizes": ["9", "9.5", "10"],
        "available_widths": ["D", "2E"],
    }

    assert _shoe_matches_variant_filters(shoe, size="9.5")
    assert _shoe_matches_variant_filters(shoe, width="wide")
    assert _shoe_matches_variant_filters(shoe, size="10", width="standard")
    assert not _shoe_matches_variant_filters(shoe, size="11")
