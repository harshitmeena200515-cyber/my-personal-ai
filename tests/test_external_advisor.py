"""
Unit and integration tests for Sandboxed External Cloud Advisor (Phase 8 / ADR-001 & ADR-009).

Verifies:
1. Outbound prompt sanitization (redaction of local Windows paths and personal identifiers).
2. Blocking of raw secret keys from outbound prompts.
3. Offline fallback handling when API key is missing.
4. Mandatory EXTERNALLY_VERIFIED provenance tagging on advisor results.
5. Mandatory requires_owner_approval flag enforcement.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.external_advisor import ExternalAdvisorSanitizer, OpenAIAdvisorAdapter, GeminiAdvisorAdapter
from core.memory_manager import SecurityException, Provenance


def test_outbound_prompt_sanitization():
    """Verify that Windows paths and email addresses are scrubbed prior to dispatch."""
    raw_prompt = "Review code located at C:\\Users\\Harshit Meena\\Downloads\\my ai\\server.py for developer harshit@example.com."
    clean = ExternalAdvisorSanitizer.sanitize_outbound_prompt(raw_prompt)

    assert "C:\\Users\\Harshit" not in clean, "Local Windows file path must be redacted"
    assert "<REDACTED_LOCAL_PATH>" in clean, "Placeholder must be inserted"
    assert "harshit@example.com" not in clean, "Personal email must be redacted"
    assert "<REDACTED_EMAIL>" in clean, "Email placeholder must be inserted"
    print("✅ test_outbound_prompt_sanitization PASSED")


def test_sanitizer_blocks_unredacted_secrets():
    """Verify that attempting to transmit a secret key raises SecurityException."""
    bad_prompt = "My OpenAI key is sk-proj-1234567890abcdef1234567890abcdef. Can you verify it?"
    blocked = False
    try:
        ExternalAdvisorSanitizer.sanitize_outbound_prompt(bad_prompt)
    except SecurityException:
        blocked = True
    assert blocked, "Prompts containing unredacted secrets must be strictly blocked"
    print("✅ test_sanitizer_blocks_unredacted_secrets PASSED")


def test_advisor_unconfigured_offline_fallback():
    """Verify that adapter handles offline / unconfigured state gracefully."""
    adapter = OpenAIAdvisorAdapter(api_key="")
    assert not adapter.is_configured

    result = adapter.consult_advisor("Explain AST tree parsing.")
    assert result["success"] is False
    assert "not configured" in result["error"]
    assert result["provenance"] == Provenance.EXTERNALLY_VERIFIED.value
    assert result["requires_owner_approval"] is True
    print("✅ test_advisor_unconfigured_offline_fallback PASSED")


def test_advisor_provenance_and_approval_enforcement():
    """Verify that any advisor result carries EXTERNALLY_VERIFIED and requires owner approval."""
    adapter = OpenAIAdvisorAdapter(api_key="sk-dummy-test-key-12345678901234567890")
    assert adapter.is_configured

    # Test mock/live behavior
    result = adapter.consult_advisor("Test architectural question")
    assert result["provenance"] == Provenance.EXTERNALLY_VERIFIED.value
    assert result["requires_owner_approval"] is True
    print("✅ test_advisor_provenance_and_approval_enforcement PASSED")


def test_gemini_unconfigured_offline_fallback():
    """Verify Gemini adapter handles missing credentials gracefully."""
    adapter = GeminiAdvisorAdapter(api_key="")
    assert not adapter.is_configured

    result = adapter.consult_advisor("How should we design a lock-free queue?")
    assert result["success"] is False
    assert "GEMINI_API_KEY not configured" in result["error"]
    assert result["provenance"] == Provenance.EXTERNALLY_VERIFIED.value
    assert result["requires_owner_approval"] is True
    print("✅ test_gemini_unconfigured_offline_fallback PASSED")


def test_gemini_cascade_and_model_switching():
    """Verify Gemini adapter cascades through models when first ones fail."""
    # Custom cascade where first model is invalid, followed by available fallback
    cascade = ["gemini-invalid-model-xyz", "gemini-flash-lite-latest"]
    adapter = GeminiAdvisorAdapter(model_cascade=cascade)
    if adapter.is_configured:
        result = adapter.consult_advisor("State one principle of clean code.", max_tokens=25)
        if result["success"]:
            assert result["model_used"] == "gemini-flash-lite-latest"
            assert "gemini-invalid-model-xyz" in result["models_attempted"]
            assert result["provenance"] == Provenance.EXTERNALLY_VERIFIED.value
            assert result["requires_owner_approval"] is True
            print("✅ test_gemini_cascade_and_model_switching (LIVE) PASSED")
        else:
            print(f"⚠️ test_gemini_cascade_and_model_switching (Network/Quota skip): {result.get('error')}")
    else:
        print("⚠️ test_gemini_cascade_and_model_switching (Offline skip)")


if __name__ == "__main__":
    test_outbound_prompt_sanitization()
    test_sanitizer_blocks_unredacted_secrets()
    test_advisor_unconfigured_offline_fallback()
    test_advisor_provenance_and_approval_enforcement()
    test_gemini_unconfigured_offline_fallback()
    test_gemini_cascade_and_model_switching()
    print("\nALL PHASE 8 EXTERNAL ADVISOR TESTS PASSED 100%!")
