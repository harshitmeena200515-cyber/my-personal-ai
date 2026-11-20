"""
Master Test Verification Suite for MY PERSONAL AI.
Runs all 14 integration and regression test suites and produces a summary report.
"""

import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
PYTHON_EXE = ROOT_DIR / ".venv" / "Scripts" / "python.exe"

TEST_SUITES = [
    ("Database Foundation & WAL", "tests/test_database.py"),
    ("Session & Token Lifecycle", "tests/test_sessions.py"),
    ("Auth & Owner Bootstrap Security", "tests/test_auth.py"),
    ("User Data Isolation & Sandbox", "tests/test_isolation.py"),
    ("Immutable Security Audit Logs", "tests/test_audit.py"),
    ("Human-in-the-Loop (HITL) Workflow", "tests/test_hitl_api.py"),
    ("Frontend Foundation & UI", "tests/test_frontend.py"),
    ("Multi-Agent Intelligence & HITL", "tests/test_agents.py"),
    ("FastAPI Server & Hardware Status", "tests/test_server.py"),
    ("Sandboxed Tools & Permissions", "tests/test_tools.py"),
    ("Hierarchical Planner & Sanitizer", "tests/test_planner.py"),
    ("Intent Reasoner & Heuristics", "tests/test_reasoning.py"),
    ("Tiered Error Recovery", "tests/test_recovery.py"),
    ("Self-Correction & Verifier", "tests/test_verifier.py"),
    ("Phase 2 Local Ollama Inference", "tests/test_phase2.py"),
    ("Phase 3 Autonomous Orchestration", "tests/test_phase3.py"),
    ("Phase 4 Final Acceptance & E2E", "tests/test_acceptance_e2e.py"),
    ("Phase 4 Deep Security & Intelligence", "tests/test_intelligence_and_security_deep.py"),
    ("Two-Part Memory Engine (Phase 5)", "tests/test_memory_engine.py"),
    ("Cross-Agent Verification Protocol (CAVP V3 / Phase 6)", "tests/test_cavp_v3.py"),
]


def run_all():
    print("=" * 70)
    print("MY PERSONAL AI — MASTER TEST SUITE EXECUTION")
    print(f"Python: {PYTHON_EXE}")
    print(f"Total Test Suites to Execute: {len(TEST_SUITES)}")
    print("=" * 70)

    results = []
    overall_start = time.time()

    for name, script_rel in TEST_SUITES:
        script_path = ROOT_DIR / script_rel
        print(f"\n▶ Running: {name} ({script_rel})...")
        suite_start = time.time()

        proc = subprocess.run(
            [str(PYTHON_EXE), str(script_path)],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
        )
        duration = time.time() - suite_start

        if proc.returncode == 0:
            print(f"  ✅ {name} PASSED in {duration:.2f}s")
            results.append((name, "PASSED", duration, ""))
        else:
            print(f"  ❌ {name} FAILED in {duration:.2f}s")
            print("  --- ERROR OUTPUT ---")
            print(proc.stderr or proc.stdout)
            print("  --------------------")
            results.append((name, "FAILED", duration, proc.stderr or proc.stdout))

    overall_duration = time.time() - overall_start

    print("\n" + "=" * 70)
    print("MASTER TEST EXECUTION SUMMARY")
    print("=" * 70)
    passed_count = sum(1 for _, status, _, _ in results if status == "PASSED")
    total_count = len(results)

    for idx, (name, status, duration, _) in enumerate(results, 1):
        icon = "✅" if status == "PASSED" else "❌"
        print(f"{idx:2d}. {icon} {name:<42} [{status}] ({duration:.2f}s)")

    print("-" * 70)
    print(f"Score: {passed_count}/{total_count} suites passed ({(passed_count/total_count)*100:.1f}%)")
    print(f"Total Wall Time: {overall_duration:.2f}s")
    print("=" * 70)

    if passed_count == total_count:
        print(f"\n🎉 ALL {total_count} TEST SUITES COMPLETED WITH 100% SUCCESS!\n")
        return 0
    else:
        print(f"\n⚠️ {total_count - passed_count} SUITE(S) FAILED.\n")
        return 1


if __name__ == "__main__":
    sys.exit(run_all())
