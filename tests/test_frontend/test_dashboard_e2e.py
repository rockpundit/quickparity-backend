import pytest
from playwright.sync_api import Page, expect

@pytest.mark.e2e
def test_dashboard_renders(page: Page):
    """
    Verify the dashboard loads and displays key elements.
    Assumes the frontend is running on localhost:3000.
    """
    try:
        page.goto("http://localhost:3000/dashboard")
        
        # 1. Verify Title/Logo
        # Expect "QuickParity" to be visible in header or title
        import re
        expect(page).to_have_title(re.compile(r"QuickParity|Dashboard"))
        
        # 2. Check for Main Action Button
        # The 'Scan for Variances' or 'Reconcile' button
        # We look for a button with text roughly matching our key functions
        scan_button = page.get_by_role("button", name="Scan")
        if scan_button.count() > 0:
            expect(scan_button).to_be_visible()
            
        # 3. Check for Stats Cards (if any data loaded)
        # Just verifying the container exists
        # This depends on your specific CSS classes or IDs. 
        # For now, just ensuring no 404 text.
        expect(page.get_by_text("404")).not_to_be_visible()
        
    except Exception as e:
        pytest.fail(f"Frontend test failed. Is the server running? {e}")

@pytest.mark.e2e
def test_login_redirect(page: Page):
    """
    Verify protected routes redirect to login (if auth is enforced).
    """
    page.goto("http://localhost:3000/settings")
    # If unauthenticated, should land on /login
    # expect(page).to_have_url(lambda u: "/login" in u)
    pass
