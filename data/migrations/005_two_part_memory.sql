-- 005_two_part_memory.sql
-- Two-Part Memory Architecture: Concise Shared Memory Table
-- Gated by explicit owner approval (ADR-009)

CREATE TABLE IF NOT EXISTS shared_memory (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    key TEXT NOT NULL,
    content TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'rule', -- 'rule', 'decision', 'preference', 'standard'
    provenance TEXT NOT NULL DEFAULT 'PENDING_APPROVAL', -- 'USER_CONFIRMED', 'AGENT_INFERRED', 'EXTERNALLY_VERIFIED', 'PENDING_APPROVAL'
    proposed_by TEXT NOT NULL, -- agent_id or 'user'
    approved_by TEXT, -- user_id who approved, or NULL if pending
    approved_at TIMESTAMP,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_shared_memory_user_cat ON shared_memory(user_id, category);
CREATE INDEX IF NOT EXISTS idx_shared_memory_provenance ON shared_memory(user_id, provenance);
CREATE INDEX IF NOT EXISTS idx_shared_memory_key ON shared_memory(user_id, key);
