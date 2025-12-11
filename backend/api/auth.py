import os
import httpx
import urllib.parse
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from backend.services.tenant import TenantManager

router = APIRouter(prefix="/auth", tags=["Auth"])

# Dependency
def get_tenant_manager():
    return TenantManager()

def get_api_base_url():
    # Helper to get the base URL for redirects. 
    # Defaults to localhost for dev, but can be overridden for prod
    return os.getenv("API_BASE_URL", "http://localhost:8000")

def get_frontend_url():
    # Helper to get the frontend URL for final redirects
    return os.getenv("FRONTEND_URL", "http://localhost:3000")

# --- STRIPE ---

@router.get("/stripe/connect")
async def connect_stripe():
    client_id = os.getenv("STRIPE_CLIENT_ID")
    is_demo = os.getenv("DEMO_MODE", "false").lower() == "true"
    
    base_url = get_api_base_url()
    redirect_uri = f"{base_url}/api/auth/stripe/callback"
    
    # 1. Check for explicit DEMO mode
    if is_demo:
         return RedirectResponse(f"{redirect_uri}?code=mock_code")

    # 2. Check for Real Credentials
    if not client_id or client_id == "ca_mock_client_id":
        # Fallback
        frontend = get_frontend_url()
        return RedirectResponse(f"{frontend}/onboarding?error=missing_config&service=Stripe")

    # Construct Stripe OAuth URL
    params = {
        "response_type": "code",
        "client_id": client_id,
        "scope": "read_write",
        "redirect_uri": redirect_uri
    }
    url = f"https://connect.stripe.com/oauth/authorize?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url)

@router.get("/stripe/callback")
async def stripe_callback(code: str, tm: TenantManager = Depends(get_tenant_manager)):
    client_secret = os.getenv("STRIPE_SECRET_KEY", "sk_test_mock")
    
    # 1. Exchange code for token
    if code == "mock_code":
        access_token = "sk_test_mock_token_123"
        stripe_user_id = "acct_mock_123"
    else:
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://connect.stripe.com/oauth/token", data={
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code"
            })
            if resp.status_code != 200:
                raise HTTPException(status_code=400, detail=f"Stripe Error: {resp.text}")
            data = resp.json()
            access_token = data.get("access_token")
            stripe_user_id = data.get("stripe_user_id")

    # 2. Save token to CURRENT tenant
    tenants = tm.list_tenants()
    if not tenants:
        tm.add_tenant("Default Merchant", "mock_sq", "mock_qbo", "mock_realm")
        tenants = tm.list_tenants()
        
    tenant = tenants[0]
    tm.update_tenant_token(tenant.id, "stripe", access_token)
    
    # Redirect back to frontend
    frontend = get_frontend_url()
    return RedirectResponse(f"{frontend}/onboarding?success=stripe")

# --- SQUARE ---

@router.get("/square/connect")
async def connect_square():
    client_id = os.getenv("SQUARE_APP_ID")
    is_demo = os.getenv("DEMO_MODE", "false").lower() == "true"
    base_url = get_api_base_url()
    redirect_uri = f"{base_url}/api/auth/square/callback"
    scope = "MERCHANT_PROFILE_READ PAYMENTS_READ SETTLEMENTS_READ BANK_ACCOUNTS_READ" 

    if is_demo:
         return RedirectResponse(f"{redirect_uri}?code=mock_code")

    if not client_id or client_id == "sq0idp-mock-client-id":
         frontend = get_frontend_url()
         return RedirectResponse(f"{frontend}/onboarding?error=missing_config&service=Square")
    
    # Sandbox URL
    base_url_sq = "https://connect.squareupsandbox.com/oauth2/authorize"
    params = {
        "client_id": client_id,
        "scope": scope,
        "redirect_uri": redirect_uri
    }
    url = f"{base_url_sq}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url)

@router.get("/square/callback")
async def square_callback(code: str, tm: TenantManager = Depends(get_tenant_manager)):
    access_token = "mock_sq_token"
    # Real app would exchange code here
    
    tenants = tm.list_tenants()
    if not tenants:
         tm.add_tenant("Default Merchant", "mock_sq", "mock_qbo", "mock_realm")
         tenants = tm.list_tenants()
         
    tenant = tenants[0]
    tm.update_tenant_token(tenant.id, "square", access_token)
    
    frontend = get_frontend_url()
    return RedirectResponse(f"{frontend}/onboarding?success=square")

# --- QUICKBOOKS ---

@router.get("/qbo/connect")
async def connect_qbo():
    client_id = os.getenv("QBO_CLIENT_ID")
    is_demo = os.getenv("DEMO_MODE", "false").lower() == "true"
    
    base_url = get_api_base_url()
    redirect_uri = f"{base_url}/api/auth/qbo/callback"
    
    if is_demo:
         return RedirectResponse(f"{redirect_uri}?code=mock_code&realmId=mock_realm_id")

    if not client_id or client_id == "mock_qbo_client_id":
         frontend = get_frontend_url()
         return RedirectResponse(f"{frontend}/onboarding?error=missing_config&service=QuickBooks")

    scope = "com.intuit.quickbooks.accounting"
    state = "security_token" 
    
    base_url_qbo = "https://appcenter.intuit.com/connect/oauth2"
    params = {
        "client_id": client_id,
        "response_type": "code",
        "scope": scope,
        "redirect_uri": redirect_uri,
        "state": state
    }
    url = f"{base_url_qbo}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url)

@router.get("/qbo/callback")
async def qbo_callback(code: str, realmId: str, tm: TenantManager = Depends(get_tenant_manager)):
    client_id = os.getenv("QBO_CLIENT_ID", "mock_qbo_client_id")
    client_secret = os.getenv("QBO_CLIENT_SECRET", "mock_qbo_secret")
    
    base_url = get_api_base_url()
    redirect_uri = f"{base_url}/api/auth/qbo/callback"
    
    if code == "mock_code":
        access_token = "mock_qbo_access_token"
        refresh_token = "mock_qbo_refresh_token"
    else:
        auth = httpx.BasicAuth(client_id, client_secret)
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer", 
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri
                },
                auth=auth
            )
            if resp.status_code != 200:
                 raise HTTPException(status_code=400, detail=f"QBO Error: {resp.text}")
            data = resp.json()
            access_token = data.get("access_token")
    
    tenants = tm.list_tenants()
    if not tenants:
         tm.add_tenant("Default Merchant", "mock_sq", "mock_qbo", realmId)
         tenants = tm.list_tenants()
         
    tenant = tenants[0]
    tm.update_tenant_token(tenant.id, "qbo", access_token)
    
    frontend = get_frontend_url()
    return RedirectResponse(f"{frontend}/onboarding?success=qbo")

# --- SHOPIFY ---

@router.get("/shopify/connect")
async def connect_shopify():
    shop = os.getenv("SHOPIFY_SHOP_DOMAIN")
    client_id = os.getenv("SHOPIFY_API_KEY")
    is_demo = os.getenv("DEMO_MODE", "false").lower() == "true"
    
    base_url = get_api_base_url()
    redirect_uri = f"{base_url}/api/auth/shopify/callback"
    
    scopes = "read_orders,read_products"
    state = "nonce_123"
    
    if is_demo:
         return RedirectResponse(f"{redirect_uri}?code=mock_code&shop=mock-shop.myshopify.com")
    
    if not shop or shop == "mock-shop" or not client_id or client_id == "mock_shopify_key":
        frontend = get_frontend_url()
        return RedirectResponse(f"{frontend}/onboarding?error=missing_config&service=Shopify")

    params = {
        "client_id": client_id,
        "scope": scopes,
        "redirect_uri": redirect_uri,
        "state": state
    }
    url = f"https://{shop}.myshopify.com/admin/oauth/authorize?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url)

@router.get("/shopify/callback")
async def shopify_callback(code: str, shop: str, tm: TenantManager = Depends(get_tenant_manager)):
    client_id = os.getenv("SHOPIFY_API_KEY", "mock_shopify_key")
    client_secret = os.getenv("SHOPIFY_API_SECRET", "mock_shopify_secret")
    
    if code == "mock_code":
        access_token = "mock_shopify_token"
    else:
        url = f"https://{shop}/admin/oauth/access_token"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code
            })
            if resp.status_code != 200:
                if "mock" in shop:
                    access_token = "mock_shopify_token_fallback"
                else:
                    raise HTTPException(status_code=400, detail=f"Shopify Error: {resp.text}")
            else:
                data = resp.json()
                access_token = data.get("access_token")

    tenants = tm.list_tenants()
    if not tenants:
         tm.add_tenant("Default Merchant", "mock_sq", "mock_qbo", "mock_realm")
         tenants = tm.list_tenants()
         
    tenant = tenants[0]
    tm.update_tenant_token(tenant.id, "shopify", access_token)
    
    frontend = get_frontend_url()
    return RedirectResponse(f"{frontend}/onboarding?success=shopify")

# --- PAYPAL ---

@router.get("/paypal/connect")
async def connect_paypal():
    client_id = os.getenv("PAYPAL_CLIENT_ID")
    is_demo = os.getenv("DEMO_MODE", "false").lower() == "true"
    
    base_url = get_api_base_url()
    redirect_uri = f"{base_url}/api/auth/paypal/callback"
    
    scope = "openid profile email https://uri.paypal.com/services/paypalhere"
    
    if is_demo:
        return RedirectResponse(f"{redirect_uri}?code=mock_code")

    if not client_id or client_id == "mock_paypal_client_id":
        frontend = get_frontend_url()
        return RedirectResponse(f"{frontend}/onboarding?error=missing_config&service=PayPal")
    
    # Sandbox URL
    base_url_pp = "https://www.sandbox.paypal.com/connect"
    params = {
        "flowEntry": "static",
        "client_id": client_id,
        "response_type": "code",
        "scope": scope,
        "redirect_uri": redirect_uri
    }
    url = f"{base_url_pp}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url)

@router.get("/paypal/callback")
async def paypal_callback(code: str, tm: TenantManager = Depends(get_tenant_manager)):
    client_id = os.getenv("PAYPAL_CLIENT_ID", "mock_paypal_client_id")
    client_secret = os.getenv("PAYPAL_CLIENT_SECRET", "mock_paypal_secret")
    
    if code == "mock_code":
        access_token = "mock_paypal_token"
    else:
        token_url = "https://api-m.sandbox.paypal.com/v1/oauth2/token"
        auth = httpx.BasicAuth(client_id, client_secret)
        async with httpx.AsyncClient() as client:
            resp = await client.post(token_url, data={
                "grant_type": "authorization_code",
                "code": code
            }, auth=auth)
            
            if resp.status_code != 200:
                 if client_id == "mock_paypal_client_id":
                     access_token = "mock_paypal_token_fallback"
                 else:
                     raise HTTPException(status_code=400, detail=f"PayPal Error: {resp.text}")
            else:
                data = resp.json()
                access_token = data.get("access_token")
    
    tenants = tm.list_tenants()
    if not tenants:
         tm.add_tenant("Default Merchant", "mock_sq", "mock_qbo", "mock_realm")
         tenants = tm.list_tenants()
         
    tenant = tenants[0]
    tm.update_tenant_token(tenant.id, "paypal", access_token)
    
    frontend = get_frontend_url()
    return RedirectResponse(f"{frontend}/onboarding?success=paypal")

# --- STATUS ---

@router.get("/status")
async def get_connection_status(tm: TenantManager = Depends(get_tenant_manager)):
    tenants = tm.list_tenants()
    if not tenants:
        return {"stripe": False, "square": False, "qbo": False, "shopify": False, "paypal": False}
    
    t = tenants[0]
    
    stripe_connected = False
    if t.encrypted_stripe_token:
        pt = tm.decrypt_token(t.encrypted_stripe_token)
        if pt: stripe_connected = True

    square_connected = False
    if t.encrypted_sq_token:
        pt = tm.decrypt_token(t.encrypted_sq_token)
        if pt and pt != "mock_sq":
             square_connected = True
        
    qbo_connected = False
    if t.encrypted_qbo_token:
        pt = tm.decrypt_token(t.encrypted_qbo_token)
        if pt and pt != "mock_qbo_token" and pt != "mock_qbo": 
             qbo_connected = True
             
    shopify_connected = False
    if t.encrypted_shopify_token:
        pt = tm.decrypt_token(t.encrypted_shopify_token)
        if pt: shopify_connected = True

    paypal_connected = False
    if t.encrypted_paypal_token:
        pt = tm.decrypt_token(t.encrypted_paypal_token)
        if pt: paypal_connected = True
             
    return {"stripe": stripe_connected, "square": square_connected, "qbo": qbo_connected, "shopify": shopify_connected, "paypal": paypal_connected}

# --- GOOGLE LOGIN ---

@router.get("/google/login")
async def google_login():
    client_id = os.getenv("GOOGLE_CLIENT_ID", "mock_google_client_id")
    base_url = get_api_base_url()
    redirect_uri = f"{base_url}/api/auth/google/callback"
    scope = "openid email profile"
    response_type = "code"
    
    if client_id == "mock_google_client_id":
        return RedirectResponse(f"{redirect_uri}?code=mock_google_code")

    base_url_google = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "response_type": response_type,
        "access_type": "offline"
    }
    url = f"{base_url_google}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url)

@router.get("/google/callback")
async def google_callback(code: str, tm: TenantManager = Depends(get_tenant_manager)):
    client_id = os.getenv("GOOGLE_CLIENT_ID", "mock_google_client_id")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "mock_google_secret")
    base_url = get_api_base_url()
    redirect_uri = f"{base_url}/api/auth/google/callback"
    
    if code == "mock_google_code":
        access_token = "mock_google_access_token"
        id_token = "mock_google_id_token"
        email = "admin@example.com"
    else:
        token_url = "https://oauth2.googleapis.com/token"
        async with httpx.AsyncClient() as client:
            resp = await client.post(token_url, data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri
            })
            if resp.status_code != 200:
                raise HTTPException(status_code=400, detail=f"Google Error: {resp.text}")
            data = resp.json()
            access_token = data.get("access_token")
            id_token = data.get("id_token")
            
    frontend = get_frontend_url()
    return RedirectResponse(f"{frontend}/onboarding?login_success=google")

# --- APPLE LOGIN ---

@router.get("/apple/login")
async def apple_login():
    client_id = os.getenv("APPLE_CLIENT_ID", "mock_apple_client_id")
    base_url = get_api_base_url()
    redirect_uri = f"{base_url}/api/auth/apple/callback"
    
    scope = "name email"
    response_type = "code"
    response_mode = "form_post"
    
    if client_id == "mock_apple_client_id":
        return RedirectResponse(f"{redirect_uri}?code=mock_apple_code")

    base_url_apple = "https://appleid.apple.com/auth/authorize"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "response_type": response_type,
        "response_mode": response_mode
    }
    url = f"{base_url_apple}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url)

@router.api_route("/apple/callback", methods=["GET", "POST"])
async def apple_callback(request: Request, tm: TenantManager = Depends(get_tenant_manager)):
    if request.method == "POST":
        form = await request.form()
        code = form.get("code")
    else:
        code = request.query_params.get("code")

    client_id = os.getenv("APPLE_CLIENT_ID", "mock_apple_client_id")
    
    if code == "mock_apple_code":
        access_token = "mock_apple_access_token"
    
    frontend = get_frontend_url()
    return RedirectResponse(f"{frontend}/onboarding?login_success=apple")
