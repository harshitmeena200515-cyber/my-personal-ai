"""
Unit and integration tests for Windows Enterprise Hardening (Phase 7 / ADR-004 & ADR-008).

Verifies:
1. Windows DPAPI (CryptProtectData & CryptUnprotectData) encryption roundtrip.
2. Windows Job Objects sandbox creation, process binding, and resource caps.
3. Subprocess timeout termination and cleanup by Job Object supervisor.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.dpapi import dpapi_encrypt, dpapi_decrypt
from core.job_objects import WindowsJobObjectSandbox


def test_dpapi_roundtrip():
    """Verify Windows DPAPI encrypts and decrypts sensitive secrets correctly."""
    secret = b"my_precious_hmac_secret_key_32bytes"
    encrypted = dpapi_encrypt(secret, description="Test Secret")

    assert encrypted != secret, "Encrypted data must not match plaintext"
    assert len(encrypted) > len(secret), "Ciphertext must include DPAPI header and MAC"

    decrypted = dpapi_decrypt(encrypted)
    assert decrypted == secret, "Decrypted data must match original plaintext"
    print("✅ test_dpapi_roundtrip PASSED")


def test_job_object_sandbox_execution():
    """Verify execution of subprocess inside Windows Job Object with memory caps."""
    with WindowsJobObjectSandbox(name=None, max_memory_mb=128, max_processes=2) as sandbox:
        code, stdout, stderr = sandbox.run_sandboxed(
            ["cmd.exe", "/c", "echo Hello from Job Object Sandbox"],
            timeout_seconds=5.0
        )
        assert code == 0, f"Process failed with code {code}, err: {stderr}"
        assert "Hello from Job Object Sandbox" in stdout
    print("✅ test_job_object_sandbox_execution PASSED")


def test_job_object_timeout_enforcement():
    """Verify that a runaway subprocess is terminated by the Job Object supervisor."""
    with WindowsJobObjectSandbox(name=None, max_memory_mb=64) as sandbox:
        # Sleep for 10s, but supervisor timeout is 1.0s
        code, stdout, stderr = sandbox.run_sandboxed(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            timeout_seconds=1.0
        )
        assert code == -1, f"Runaway process should be killed with -1, got {code}"
        assert "Execution Timeout" in stderr
    print("✅ test_job_object_timeout_enforcement PASSED")


if __name__ == "__main__":
    test_dpapi_roundtrip()
    test_job_object_sandbox_execution()
    test_job_object_timeout_enforcement()
    print("\nALL PHASE 7 WINDOWS HARDENING TESTS PASSED 100%!")
