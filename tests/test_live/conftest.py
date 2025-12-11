import pytest
import os
from dotenv import load_dotenv

load_dotenv()

@pytest.fixture(scope="module")
def vcr_config():
    return {
        "filter_headers": [
            "Authorization", 
            "Stripe-Signature",
            "X-Shopify-Access-Token", 
            "Square-Version"
        ],
        "filter_query_parameters": ["code", "state", "key", "token"],
        "filter_post_data_parameters": ["client_id", "client_secret", "code", "refresh_token"],
        "ignore_localhost": True,
        "record_mode": "once", # Record once, then replay
    }

@pytest.fixture
def stripe_live_client():
    from backend.connectors.stripe import StripeClient
    api_key = os.getenv("STRIPE_SECRET_KEY")
    if not api_key:
        pytest.skip("STRIPE_SECRET_KEY not found in .env")
    return StripeClient(access_token=api_key)

@pytest.fixture
async def square_live_client():
    from backend.connectors.square import SquareClient
    token = os.getenv("SQUARE_ACCESS_TOKEN")
    if not token:
        pytest.skip("SQUARE_ACCESS_TOKEN not found in .env")
    client = SquareClient(access_token=token, environment="sandbox")
    yield client
    await client.close()

@pytest.fixture
async def qbo_live_client():
    from backend.connectors.qbo import QBOClient
    realm = os.getenv("QBO_REALM_ID")
    token = os.getenv("QBO_ACCESS_TOKEN")
    if not realm or not token:
        pytest.skip("QBO credentials not found in .env")
    client = QBOClient(realm_id=realm, access_token=token)
    yield client
    await client.close()
