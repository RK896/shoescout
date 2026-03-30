import pytest
import re
from scraper import zappos_api, nike, finishline, brooks, runningwarehouse_api

def validate_shoe_contract(shoe):
    """Utility to check if a shoe object matches our expected schema."""
    assert "model" in shoe and isinstance(shoe["model"], str) and len(shoe["model"]) > 0
    assert "brand" in shoe and isinstance(shoe["brand"], str) and len(shoe["brand"]) > 0
    assert "price" in shoe and isinstance(shoe["price"], str)
    # Price should match typical patterns: $129.99, 129.99, etc.
    assert re.search(r"\d+\.?\d*", shoe["price"])
    assert "retailer" in shoe and isinstance(shoe["retailer"], str)
    assert "link" in shoe and isinstance(shoe["link"], str) and shoe["link"].startswith("http")
    assert "image" in shoe and isinstance(shoe["image"], str)

@pytest.mark.integration
def test_runningwarehouse_scraper_contract():
    shoes = runningwarehouse_api.scrape_runningwarehouse()
    assert isinstance(shoes, list)
    if len(shoes) > 0:
        validate_shoe_contract(shoes[0])

@pytest.mark.integration
def test_zappos_scraper_contract():
    shoes = zappos_api.scrape_zappos()
    assert isinstance(shoes, list)
    if len(shoes) > 0:
        validate_shoe_contract(shoes[0])

@pytest.mark.integration
def test_nike_scraper_contract():
    # Only if Nike scraper is working (it uses selenium sometimes, let's see)
    shoes = nike.scrape_nike()
    assert isinstance(shoes, list)
    if len(shoes) > 0:
        validate_shoe_contract(shoes[0])

@pytest.mark.integration
def test_brooks_scraper_contract():
    shoes = brooks.scrape_brooks()
    assert isinstance(shoes, list)
    if len(shoes) > 0:
        validate_shoe_contract(shoes[0])

@pytest.mark.integration
def test_finishline_scraper_contract():
    shoes = finishline.scrape_finishline()
    assert isinstance(shoes, list)
    if len(shoes) > 0:
        validate_shoe_contract(shoes[0])
