import os
import secrets
from backend.services.tenant import TenantManager

# Initialize TenantManager
tm = TenantManager()

# Generate fake tokens for the mandatory fields
fake_sq_token = f"sq0atp-{secrets.token_urlsafe(20)}"
fake_qbo_token = f"eyJl...{secrets.token_urlsafe(50)}" # Fake JWT-ish
fake_qbo_realm = ''.join(secrets.choice("0123456789") for _ in range(15))

try:
    # Create the tenant
    tenant_name = "Pro User"
    tenant = tm.add_tenant(
        name=tenant_name,
        sq_token=fake_sq_token,
        qbo_token=fake_qbo_token,
        qbo_realm=fake_qbo_realm,
        subscription_tier="paid"
    )
    
    print(f"Successfully created tenant '{tenant.name}' with ID: {tenant.id}")
    print(f"Subscription Tier: {tenant.subscription_tier}")

except ValueError as e:
    print(f"Error: {e}")

# Verify
print("\n--- Verification ---")
check_tenant = next((t for t in tm.list_tenants() if t.name == tenant_name), None)
if check_tenant:
    print(f"Found tenant in DB: {check_tenant.name}, Tier: {check_tenant.subscription_tier}")
else:
    print("Failed to find tenant in DB verification.")
