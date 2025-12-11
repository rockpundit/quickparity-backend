import os
import httpx
import asyncio
from dotenv import load_dotenv
import urllib.parse
import base64

load_dotenv()

CLIENT_ID = os.getenv("QBO_CLIENT_ID")
CLIENT_SECRET = os.getenv("QBO_CLIENT_SECRET")
CODE = "XAB11765358952KMECF70jwB8KY9pYP9Met9361FYQ7lhemkr4" # From user
REALM_ID = "9341455894883387"

# Standard Playground URI
PLAYGROUND_URI = "https://developer.intuit.com/v2/OAuth2Playground/RedirectUrl"
# Local App URI
LOCAL_URI = "http://localhost:8000/api/auth/qbo/callback"

async def try_exchange(redirect_uri, name):
    print(f"\n--- Trying {name} ---")
    print(f"Redirect URI: {redirect_uri}")
    
    url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
    auth = httpx.BasicAuth(CLIENT_ID, CLIENT_SECRET)
    
    data = {
        "grant_type": "authorization_code",
        "code": CODE,
        "redirect_uri": redirect_uri,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    print(f"Sending request to {url}...")
    try:
        async with httpx.AsyncClient() as client:
            # Removing auth=auth, sending in body
            resp = await client.post(url, data=data, headers=headers)
            print(f"Status: {resp.status_code}")
            print(f"Response: {resp.text}")
            
            if resp.status_code == 200:
                print("SUCCESS!")
                return resp.json()
    except Exception as e:
        print(f"Exception: {e}")
        
    return None

async def main():
    print(f"Client ID: {CLIENT_ID}")
    print(f"Client Secret: {CLIENT_SECRET[:5]}...")
    
    # Try Local first
    res = await try_exchange(LOCAL_URI, "Local App URI")
    if not res:
        # Try Playground
        res = await try_exchange(PLAYGROUND_URI, "Intuit Playground URI")

if __name__ == "__main__":
    asyncio.run(main())
