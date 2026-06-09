"""
Smoke tests for the /settings route, nav.js entry, and settings.html constraints.

Phase 4 — settings page + nav entry + /settings route.
"""
import re
import pathlib

import pytest
from fastapi.testclient import TestClient

from haandvaerker.main import app

_STATIC = pathlib.Path(__file__).parent.parent / "src" / "haandvaerker" / "static"


@pytest.fixture(name="plain_client")
def plain_client_fixture():
    """TestClient with no auth overrides — /settings returns raw HTML."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def test_settings_route_serves_page(plain_client: TestClient) -> None:
    """GET /settings returns 200 and the HTML contains all five section markers."""
    response = plain_client.get("/settings")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    for section_id in [
        "section-company",
        "section-logo",
        "section-email",
        "section-ai",
        "section-prompts",
    ]:
        assert section_id in body, f"Missing section marker: {section_id}"


def test_nav_has_settings_link() -> None:
    """nav.js SECTIONS array contains an entry with label 'Indstillinger' and href '/settings'."""
    nav_text = (_STATIC / "nav.js").read_text(encoding="utf-8")
    assert "Indstillinger" in nav_text, "nav.js is missing 'Indstillinger' label"
    assert "/settings" in nav_text, "nav.js is missing '/settings' href"


def test_password_field_has_no_value() -> None:
    """No password input in settings.html has a 'value=' attribute."""
    html = (_STATIC / "settings.html").read_text(encoding="utf-8")
    # Find all password input tags
    password_inputs = re.findall(
        r'<input[^>]+type=["\']password["\'][^>]*>', html, re.IGNORECASE
    )
    # Also catch inputs where type comes after other attributes
    password_inputs += re.findall(
        r'<input[^>]+password[^>]*type=["\']password["\'][^>]*>', html, re.IGNORECASE
    )
    assert password_inputs, "Expected at least one password input field in settings.html"
    for field in password_inputs:
        assert "value=" not in field, (
            f"Password input must never have 'value=' attribute, found: {field}"
        )


def test_prompt_details_not_open_by_default() -> None:
    """The prompt <details> element must not have the 'open' attribute."""
    html = (_STATIC / "settings.html").read_text(encoding="utf-8")
    assert 'id="section-prompts"' in html, "Missing <details id=\"section-prompts\">"
    # The element must not be open by default
    assert '<details id="section-prompts" open' not in html, (
        "Prompt details element must not have 'open' attribute (should be collapsed by default)"
    )
    assert "<details id=\"section-prompts\" open" not in html
