import os
import io

from src import create_app

# CRITICAL: Set environment variable before ANY local imports happen
os.environ["HOSPITAL_API_URL"] = "https://mock-hospital-api.com"

import pytest


@pytest.fixture
def app():
    # Pass testing flag
    app = create_app({"TESTING": True})
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def valid_csv_bytes():
    return b"name,address,phone\nHospital A,123 Main St,555-0001\nHospital B,456 Oak St,555-0002"


@pytest.fixture
def invalid_csv_bytes():
    return b"wrong,headers\nData 1,Data 2"
