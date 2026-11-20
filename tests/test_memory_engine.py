"""
Unit and integration tests for Two-Part Memory Architecture Engine (Phase 5 / ADR-009).

Verifies:
1. Private agent memory isolation.
2. Data sanitizer rejecting API keys, passwords, bearer tokens, and secrets.
3. Shared memory proposal (PENDING_APPROVAL) and owner approval (USER_CONFIRMED).
4. Owner access controls and unauthorized approval blocking.
"""

import sys
import tempfile
import uuid
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.memory_manager import (
    MemoryManager,
    PrivateAgentMemory,
    SharedMemoryStore,
    DataSanitizer,
    Provenance,
    SecurityException,
)
from data.db import DatabaseManager


def test_private_memory_isolation():
    """Verify that Agent A and Agent B have strictly isolated working memories."""
    user_id = "user-123"
    mem_mgr = MemoryManager()
    
    coder_mem = mem_mgr.get_private_memory("coder_agent", user_id)
    cyber_mem = mem_mgr.get_private_memory("cyber_agent", user_id)
    
    # Coder writes task scratchpad and private heuristics
    coder_mem.set_scratchpad("current_ast", {"nodes": 42})
    coder_mem.record_heuristic("python_imports", "avoid circular imports in utils", successful=True)
    
    # Cyber agent should have empty scratchpad and separate heuristics
    assert cyber_mem.get_scratchpad("current_ast") is None, "Cyber agent should not see Coder scratchpad"
    assert len(cyber_mem.get_heuristics("python_imports")) == 0, "Cyber agent should not see Coder heuristics"
    
    # Coder agent can read its own data
    assert coder_mem.get_scratchpad("current_ast") == {"nodes": 42}
    assert len(coder_mem.get_heuristics("python_imports")) == 1
    
    # Clearing scratchpad does not wipe persistent heuristics
    coder_mem.clear_scratchpad()
    assert coder_mem.get_scratchpad("current_ast") is None
    assert len(coder_mem.get_heuristics("python_imports")) == 1
    print("✅ test_private_memory_isolation PASSED")


def test_data_sanitizer_blocks_secrets():
    """Verify that DataSanitizer blocks unredacted API keys, bearer tokens, and passwords."""
    mem = PrivateAgentMemory("coder", "user-1")
    
    # Attempting to store an OpenAI key must raise SecurityException
    blocked = False
    try:
        mem.set_scratchpad("leaked_key", "sk-proj-1234567890abcdef1234567890abcdef")
    except SecurityException:
        blocked = True
    assert blocked, "Must block raw OpenAI API keys"
    
    # Attempting to store a Bearer token
    blocked = False
    try:
        mem.record_heuristic("auth", "Use Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9 for all calls", successful=True)
    except SecurityException:
        blocked = True
    assert blocked, "Must block bearer tokens"
    
    # Attempting to store password strings
    blocked = False
    try:
        mem.record_heuristic("login", "password='SuperSecretPassword123!'", successful=False)
    except SecurityException:
        blocked = True
    assert blocked, "Must block passwords"

    # Safe text must pass without error
    mem.set_scratchpad("safe_var", "Standard mathematical constant: pi=3.14159")
    assert mem.get_scratchpad("safe_var") == "Standard mathematical constant: pi=3.14159"
    print("✅ test_data_sanitizer_blocks_secrets PASSED")


def test_shared_memory_proposal_and_approval_workflow():
    """Verify the two-part shared memory approval gate (ADR-009)."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test_memory.db"
        db_mgr = DatabaseManager(str(db_path))
        db_mgr.run_migrations()
        
        user_id = str(uuid.uuid4())
        db_mgr.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?);",
            (user_id, "harshit_owner", "$argon2id$mockhash")
        )
        
        shared_store = SharedMemoryStore(db_mgr)
        
        # Step 1: Agent proposes a rule -> PENDING_APPROVAL
        proposal = shared_store.propose_entry(
            user_id=user_id,
            key="max_recursion_depth",
            content="Limit recursive search depth to 5 levels",
            category="rule",
            proposed_by="research_agent"
        )
        assert proposal["provenance"] == Provenance.PENDING_APPROVAL.value
        
        # Step 2: Agent querying approved rules should NOT see pending proposals
        approved = shared_store.get_approved_rules(user_id)
        assert len(approved) == 0, "Pending rules must not be returned in approved rules"
        
        # It should appear in pending proposals
        pending = shared_store.get_pending_proposals(user_id)
        assert len(pending) == 1
        assert pending[0]["key"] == "max_recursion_depth"
        
        # Step 3: Owner Harshit approves the entry -> USER_CONFIRMED
        approved_entry = shared_store.approve_entry(proposal["id"], user_id)
        assert approved_entry["provenance"] == Provenance.USER_CONFIRMED.value
        assert approved_entry["approved_by"] == user_id
        
        # Step 4: Now querying approved rules returns the confirmed rule
        approved = shared_store.get_approved_rules(user_id)
        assert len(approved) == 1
        assert approved[0]["key"] == "max_recursion_depth"
        assert approved[0]["provenance"] == Provenance.USER_CONFIRMED.value
        print("✅ test_shared_memory_proposal_and_approval_workflow PASSED")


def test_shared_memory_rejects_unauthorized_approval():
    """Verify that an unauthorized user cannot approve another user's memory."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test_memory_sec.db"
        db_mgr = DatabaseManager(str(db_path))
        db_mgr.run_migrations()
        
        user_id = str(uuid.uuid4())
        db_mgr.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?);",
            (user_id, "harshit_owner", "$argon2id$mockhash")
        )
        
        shared_store = SharedMemoryStore(db_mgr)
        proposal = shared_store.propose_entry(
            user_id=user_id,
            key="safety_policy",
            content="Always verify tool return code",
            category="rule",
            proposed_by="cyber_agent"
        )
        
        # Attacker tries to approve
        blocked = False
        try:
            shared_store.approve_entry(proposal["id"], "attacker_user_id")
        except SecurityException:
            blocked = True
        assert blocked, "Unauthorized approval must be rejected with SecurityException"
        print("✅ test_shared_memory_rejects_unauthorized_approval PASSED")


if __name__ == "__main__":
    test_private_memory_isolation()
    test_data_sanitizer_blocks_secrets()
    test_shared_memory_proposal_and_approval_workflow()
    test_shared_memory_rejects_unauthorized_approval()
    print("\nALL PHASE 5 TWO-PART MEMORY TESTS PASSED 100%!")
