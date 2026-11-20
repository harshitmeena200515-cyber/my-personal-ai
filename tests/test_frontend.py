"""
Frontend Integration Test Suite for MY PERSONAL AI (Milestones C & D).

Verifies:
  1. Root endpoint serves the modern modular frontend.
  2. All 4 modular CSS stylesheets are served correctly.
  3. Both ES6 JavaScript files are served correctly.
  4. All 10 mandatory UI requirements from specification are present in DOM.
  5. Dark and light theme tokens and responsive layouts are supported.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from server import app

client = TestClient(app)


def test_frontend_root_served():
    """Verify that root / serves the modern frontend."""
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    html = res.text

    # Core requirements
    assert "MY PERSONAL AI" in html
    assert "100% Offline" in html
    assert "/frontend/css/variables.css" in html
    assert "/frontend/css/layout.css" in html
    assert "/frontend/css/chat.css" in html
    assert "/frontend/css/components.css" in html
    assert "/frontend/js/api.js" in html
    assert "/frontend/js/app.js" in html
    print("✅ test_frontend_root_served PASSED")


def test_frontend_static_assets():
    """Verify that all CSS and JS files are served with status 200 and valid content."""
    # CSS Assets
    css_files = [
        "/frontend/css/variables.css",
        "/frontend/css/layout.css",
        "/frontend/css/chat.css",
        "/frontend/css/components.css",
    ]
    for css_url in css_files:
        res = client.get(css_url)
        assert res.status_code == 200, f"Failed to load {css_url}"
        assert len(res.text) > 50

    # Check that variables.css contains dark and light themes
    var_res = client.get("/frontend/css/variables.css")
    assert "--bg-app" in var_res.text
    assert '[data-theme="light"]' in var_res.text

    # JS Assets
    js_files = [
        "/frontend/js/api.js",
        "/frontend/js/app.js",
    ]
    for js_url in js_files:
        res = client.get(js_url)
        assert res.status_code == 200, f"Failed to load {js_url}"
        assert len(res.text) > 100

    api_res = client.get("/frontend/js/api.js")
    assert "class ApiClient" in api_res.text
    assert "streamChat" in api_res.text
    assert "streamThink" in api_res.text

    app_res = client.get("/frontend/js/app.js")
    assert "init" in app_res.text
    assert "handleSendMessage" in app_res.text

    print("✅ test_frontend_static_assets PASSED")


def test_all_10_ui_requirements_present():
    """Verify presence of all 10 required UI features in the HTML DOM."""
    res = client.get("/")
    assert res.status_code == 200
    html = res.text

    # 1. Modern AI assistant chat interface & branding
    assert "MY PERSONAL AI" in html
    assert "PRO v0.4" in html

    # 2. Chat message area
    assert 'id="chat-stream"' in html

    # 3. Message input and send button
    assert 'id="chat-textarea"' in html
    assert 'id="send-btn"' in html

    # 4. Voice interaction button placeholder
    assert 'id="voice-btn"' in html
    assert "voice-btn-placeholder" in html

    # 5. Agent status indicator
    assert "Local Engine (qwen2.5-coder:3b)" in html
    assert "RTX 3050" in html

    # 6. Task planning and execution progress panel
    assert 'id="planning-steps-container"' in html
    assert "Autonomous Execution Pipeline" in html

    # 7. Memory and activity section
    assert 'id="tab-memory-content"' in html
    assert "Tri-Layer Memory State" in html

    # 8. Human approval interface
    assert 'id="hitl-container"' in html
    assert "Human-in-the-Loop (HITL) Approvals" in html

    # 9. Security and permission settings
    assert 'id="tab-security-content"' in html
    assert "Access Control & Role (RBAC)" in html

    # 10. Responsive desktop and mobile layout
    assert 'id="sidebar-toggle-btn"' in html
    assert 'id="inspector-toggle-btn"' in html
    assert 'id="auth-modal"' in html

    print("✅ test_all_10_ui_requirements_present PASSED")


if __name__ == "__main__":
    test_frontend_root_served()
    test_frontend_static_assets()
    test_all_10_ui_requirements_present()
    print("\nALL FRONTEND TESTS PASSED SUCCESSFULLY!")
