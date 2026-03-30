import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
from alerts import check_and_fire_alerts

@pytest.fixture
def mock_db():
    db = MagicMock()
    return db

@patch("alerts.send_alert_email")
def test_check_and_fire_alerts_no_alerts(mock_send, mock_db):
    mock_db["alerts"].find.return_value = []
    fired = check_and_fire_alerts(mock_db)
    assert fired == 0
    mock_send.assert_not_called()

@patch("alerts.send_alert_email")
def test_check_and_fire_alerts_no_price_drop(mock_send, mock_db):
    # Alert for $100
    alert = {
        "_id": "alert1",
        "email": "user@example.com",
        "shoe_model": "Nike Pegasus 41",
        "target_price": 100.0,
        "active": True,
        "last_triggered": None
    }
    mock_db["alerts"].find.return_value = [alert]
    
    # Shoe is $120
    shoe = {
        "brand": "Nike",
        "image": "img.jpg",
        "retailers": [{"retailer": "Nike", "price": "$120.00", "link": "http://..."}]
    }
    mock_db["shoes"].find_one.return_value = shoe
    
    fired = check_and_fire_alerts(mock_db)
    assert fired == 0
    mock_send.assert_not_called()

@patch("alerts.send_alert_email")
def test_check_and_fire_alerts_price_drop_fires(mock_send, mock_db):
    mock_send.return_value = True
    
    # Alert for $100
    alert = {
        "_id": "alert1",
        "email": "user@example.com",
        "shoe_model": "Nike Pegasus 41",
        "target_price": 100.0,
        "active": True,
        "last_triggered": None
    }
    mock_db["alerts"].find.return_value = [alert]
    
    # Shoe is $90
    shoe = {
        "brand": "Nike",
        "image": "img.jpg",
        "retailers": [{"retailer": "Nike", "price": "$90.00", "link": "http://..."}]
    }
    mock_db["shoes"].find_one.return_value = shoe
    
    fired = check_and_fire_alerts(mock_db)
    assert fired == 1
    mock_send.assert_called_once()
    mock_db["alerts"].update_one.assert_called_once()

@patch("alerts.send_alert_email")
def test_check_and_fire_alerts_cooldown(mock_send, mock_db):
    # Alert triggered 2 hours ago
    last_triggered = datetime.now(timezone.utc) - timedelta(hours=2)
    alert = {
        "_id": "alert1",
        "email": "user@example.com",
        "shoe_model": "Nike Pegasus 41",
        "target_price": 100.0,
        "active": True,
        "last_triggered": last_triggered
    }
    mock_db["alerts"].find.return_value = [alert]
    
    # Shoe is $90 (should trigger but cooldown prevents it)
    shoe = {
        "brand": "Nike",
        "image": "img.jpg",
        "retailers": [{"retailer": "Nike", "price": "$90.00", "link": "http://..."}]
    }
    mock_db["shoes"].find_one.return_value = shoe
    
    fired = check_and_fire_alerts(mock_db)
    assert fired == 0
    mock_send.assert_not_called()
