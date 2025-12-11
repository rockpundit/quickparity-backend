from backend.services.tenant import TenantManager
import sqlite3

# Raw token from user, stripped of whitespace/newlines
ACCESS_TOKEN = (
    "eyJhbGciOiJkaXIiLCJlbmMiOiJBMTI4Q0JDLUhTMjU2IiwieC5vcmciOiJIMCJ9..oYAhKEMXo3lAvii_7SaN0w"
    ".hkJiSNQLJAtpaqd0M8z2wWKWHeRxr0FVK9nGp8L1b2lpBb6OtZfeu9Sjcfh1cV2Tul_GJ7UDMNu-AfQS85bg3PWa0UeiK3Prv6zWknB9Khjs"
    "-EeepXUqcmVsfrK6JG394_6A8Cqan4IW8pdNVWecLxCEnLdCbFjqMyu4tBBWWVFAnOumxh7Qy50wTx9upAzfHwT1Xq5LR7kzMOy9qgfel_I0ovGE"
    "6Wwi51PVSByCd61ElB9Lm4apdxUv-PvjNf-LuOVc3QssDG2ciBkfko0b-UQUw0nfplWyE_z_cm14XTze57UnC7tg3wArctuTX4UZ6P"
    "-8XGyAelGdjv2czhW3YpF1hv7en9S9sOgZew_1x66blp5E2UcQ6LfJHNJ3ZpS0dxIWmppXgxiyFlBrdnjbg1Sxd"
    "-ei9Sy1Q9nstMCnFGnulpUgOKIrYvKuf0KKj5qgJtx7TN2UcJGYF-uJPXKpqQ0Pwzbuzc5wXQrnTeH8geo.cmksnD84tsqdrBkjCZ2bWw"
)
REALM_ID = "9341455894883387"

# Note: We aren't saving the Refresh Token because the current schema doesn't appear to support it. 
# This access token will last 60 minutes.
REFRESH_TOKEN = "RT1-122-H0-1774085012q0zbnm52i2f456abrc6i"

def inject_token():
    tm = TenantManager()
    
    # 1. Get Tenant
    tenants = tm.list_tenants()
    if not tenants:
        print("No tenants found. Creating default...")
        tm.add_tenant("Default Merchant", "mock_sq", "mock_qbo", REALM_ID)
        tenants = tm.list_tenants()
        
    tenant = tenants[0]
    print(f"Injecting token for tenant: {tenant.id} ({tenant.name})")
    
    # 2. Update Token using Manager (handles encryption)
    tm.update_tenant_token(tenant.id, "qbo", ACCESS_TOKEN)
    tm.update_tenant_token(tenant.id, "qbo_refresh", REFRESH_TOKEN)
    
    # 3. Update Realm ID (Manager doesn't have a method for this update, do raw SQL)
    conn = sqlite3.connect(tm.db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE tenants SET qbo_realm_id = ? WHERE id = ?", (REALM_ID, tenant.id))
    conn.commit()
    conn.close()
    
    print("SUCCESS: Token injected.")

if __name__ == "__main__":
    inject_token()
