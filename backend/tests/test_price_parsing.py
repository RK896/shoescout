import pytest
from main import parse_price

def test_parse_simple_price():
    assert parse_price("$129.99") == 129.99
    assert parse_price("129.99") == 129.99

def test_parse_comma_price():
    assert parse_price("$1,299.00") == 1299.00
    assert parse_price("1,299.00") == 1299.00

def test_parse_missing_dollar_sign():
    assert parse_price("130") == 130.0

def test_parse_text_with_price():
    assert parse_price("On sale for $89.00") == 89.0
    assert parse_price("Now only $74.95!") == 74.95

def test_parse_invalid_price():
    assert parse_price("") == float("inf")
    assert parse_price(None) == float("inf")
    assert parse_price("Price coming soon") == float("inf")

def test_parse_multiple_digits():
    # regex matches first digit group
    assert parse_price("Was $140, now $110") == 140.0
