import pytest
from unittest.mock import MagicMock, call
from main import add_shoes_to_db

@pytest.fixture
def mock_db():
    db = MagicMock()
    return db

def test_add_new_shoe(mock_db):
    shoes = [
        {"model": "Nike Pegasus 41", "brand": "Nike", "price": "$130.00", "image": "img.jpg", "retailer": "Nike", "link": "link"}
    ]
    mock_db["shoes"].find_one.return_value = None
    
    add_shoes_to_db(shoes, mock_db)
    
    # New shoe uses 1 update_one with upsert=True
    mock_db["shoes"].update_one.assert_called_once()
    args, kwargs = mock_db["shoes"].update_one.call_args
    assert args[0] == {"model": "Nike Pegasus 41"}
    assert "$set" in args[1]
    assert "$addToSet" in args[1]
    assert "$push" in args[1] # includes price history
    assert kwargs.get("upsert") is True

def test_add_existing_shoe_new_retailer(mock_db):
    shoes = [
        {"model": "Nike Pegasus 41", "brand": "Nike", "price": "$120.00", "image": "img.jpg", "retailer": "Dick's", "link": "link2"}
    ]
    existing_shoe = {
        "model": "Nike Pegasus 41",
        "brand": "Nike",
        "retailers": [{"retailer": "Nike", "price": "$130.00", "link": "link1"}]
    }
    mock_db["shoes"].find_one.return_value = existing_shoe
    
    add_shoes_to_db(shoes, mock_db)
    
    # Should be 2 calls: one for $addToSet (retailer) and one for $push (price_history)
    assert mock_db["shoes"].update_one.call_count == 2
    
    first_call = mock_db["shoes"].update_one.call_args_list[0]
    assert "$addToSet" in first_call[0][1]
    
    second_call = mock_db["shoes"].update_one.call_args_list[1]
    assert "$push" in second_call[0][1]

def test_add_existing_shoe_lower_price(mock_db):
    shoes = [
        {"model": "Nike Pegasus 41", "brand": "Nike", "price": "$110.00", "image": "img.jpg", "retailer": "Nike", "link": "link1"}
    ]
    existing_shoe = {
        "model": "Nike Pegasus 41",
        "brand": "Nike",
        "retailers": [{"retailer": "Nike", "price": "$130.00", "link": "link1"}]
    }
    mock_db["shoes"].find_one.return_value = existing_shoe
    
    add_shoes_to_db(shoes, mock_db)
    
    # Should be 2 calls: one for $set (price) and one for $push (price_history)
    assert mock_db["shoes"].update_one.call_count == 2
    
    first_call = mock_db["shoes"].update_one.call_args_list[0]
    assert first_call[0][0] == {"model": "Nike Pegasus 41", "retailers.retailer": "Nike"}
    assert first_call[0][1]["$set"]["retailers.$.price"] == "$110.00"
    
    second_call = mock_db["shoes"].update_one.call_args_list[1]
    assert "$push" in second_call[0][1]

def test_add_existing_shoe_higher_price_no_update(mock_db):
    shoes = [
        {"model": "Nike Pegasus 41", "brand": "Nike", "price": "$140.00", "image": "img.jpg", "retailer": "Nike", "link": "link1"}
    ]
    existing_shoe = {
        "model": "Nike Pegasus 41",
        "brand": "Nike",
        "retailers": [{"retailer": "Nike", "price": "$130.00", "link": "link1"}]
    }
    mock_db["shoes"].find_one.return_value = existing_shoe
    
    add_shoes_to_db(shoes, mock_db)
    
    # Should be 1 call: only the $push to price_history
    mock_db["shoes"].update_one.assert_called_once()
    args, kwargs = mock_db["shoes"].update_one.call_args
    assert "$push" in args[1]
    assert "price_history" in args[1]["$push"]


def test_add_new_shoe_persists_size_variants(mock_db):
    shoes = [
        {
            "model": "Brooks Ghost 16",
            "brand": "Brooks",
            "price": "$120.00",
            "image": "img.jpg",
            "retailer": "Holabird Sports",
            "link": "link",
            "size_variants": [
                {"size": "10.5", "width": "Wide", "available": True, "link": "variant-link"}
            ],
        }
    ]
    mock_db["shoes"].find_one.return_value = None

    add_shoes_to_db(shoes, mock_db)

    args, kwargs = mock_db["shoes"].update_one.call_args
    assert kwargs.get("upsert") is True
    stored_variant = args[1]["$set"]["size_variants"][0]
    assert stored_variant["size"] == "10.5"
    assert stored_variant["width"] == "Wide"
    assert stored_variant["available"] is True
    assert stored_variant["link"] == "variant-link"
    assert args[1]["$set"]["available_sizes"] == ["10.5"]
    assert args[1]["$set"]["available_widths"] == ["Wide"]


def test_add_new_shoe_persists_variant_metadata(mock_db):
    shoes = [
        {
            "model": "Holabird Sample",
            "brand": "Nike",
            "price": "$120.00",
            "image": "img.jpg",
            "retailer": "Holabird Sports",
            "link": "link",
            "gender": "Men's",
            "size_variants": [
                {
                    "size": "10",
                    "width": "D",
                    "price": "$120.00",
                    "list_price": "$140.00",
                    "available": True,
                    "variant_id": "a1",
                    "link": "variant-link",
                },
                {
                    "size": "10.5",
                    "width": "2E",
                    "price": "$125.00",
                    "list_price": "$145.00",
                    "available": True,
                    "variant_id": "a2",
                    "link": "variant-link-2",
                },
            ],
        }
    ]
    mock_db["shoes"].find_one.return_value = None

    add_shoes_to_db(shoes, mock_db)

    mock_db["shoes"].update_one.assert_called_once()
    args, kwargs = mock_db["shoes"].update_one.call_args
    set_fields = args[1]["$set"]
    assert set_fields["gender"] == "Men's"
    assert set_fields["size_variants"][0]["size"] == "10"
    assert set_fields["available_sizes"] == ["10", "10.5"]
    assert set_fields["available_widths"] == ["2E", "D"]
    assert kwargs.get("upsert") is True


def test_add_existing_shoe_merges_variant_metadata(mock_db):
    shoes = [
        {
            "model": "Holabird Sample",
            "brand": "Nike",
            "price": "$110.00",
            "image": "img.jpg",
            "retailer": "Holabird Sports",
            "link": "link",
            "size_variants": [
                {
                    "size": "10",
                    "width": "D",
                    "price": "$110.00",
                    "list_price": "$140.00",
                    "available": True,
                    "variant_id": "a1",
                    "link": "variant-link",
                },
                {
                    "size": "10.5",
                    "width": "2E",
                    "price": "$125.00",
                    "list_price": "$145.00",
                    "available": True,
                    "variant_id": "a2",
                    "link": "variant-link-2",
                },
            ],
        }
    ]
    existing_shoe = {
        "model": "Holabird Sample",
        "brand": "Nike",
        "retailers": [{"retailer": "Nike", "price": "$130.00", "link": "link1"}],
        "size_variants": [
            {
                "size": "9.5",
                "width": "D",
                "price": "$128.00",
                "list_price": "$145.00",
                "available": True,
                "variant_id": "a0",
                "link": "variant-link-0",
            }
        ],
    }
    mock_db["shoes"].find_one.return_value = existing_shoe

    add_shoes_to_db(shoes, mock_db)

    assert mock_db["shoes"].update_one.call_count == 2
    first_call = mock_db["shoes"].update_one.call_args_list[0]
    set_fields = first_call[0][1]["$set"]
    assert set_fields["size_variants"][0]["size"] == "9.5"
    assert set_fields["available_sizes"] == ["10", "10.5", "9.5"]
    assert set_fields["available_widths"] == ["2E", "D"]
