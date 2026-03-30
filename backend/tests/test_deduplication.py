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
