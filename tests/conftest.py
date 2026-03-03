import pytest
from unittest.mock import patch

# Mock init_db before importing app to avoid DB connection errors at import time
with patch("database.init_db"):
    from app import app as flask_app

@pytest.fixture
def app():
    flask_app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test_secret_key"
    })
    return flask_app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def runner(app):
    return app.test_cli_runner()
