-- Migration 004: Tamper-Resistant Cryptographic Audit Log & HITL Expiration Hardening
-- MY PERSONAL AI Phase 4 Acceptance Hardening

-- 1. Add cryptographic hash chaining columns to audit_logs
ALTER TABLE audit_logs ADD COLUMN prev_hash TEXT DEFAULT 'GENESIS';
ALTER TABLE audit_logs ADD COLUMN entry_hash TEXT DEFAULT NULL;

-- 2. Add expiration column to hitl_approvals
ALTER TABLE hitl_approvals ADD COLUMN expires_at TIMESTAMP DEFAULT NULL;

-- 3. Database Triggers for Immutable Audit Logs
-- Prevent any UPDATE on audit_logs table
CREATE TRIGGER IF NOT EXISTS prevent_audit_log_update
BEFORE UPDATE ON audit_logs
BEGIN
    SELECT RAISE(FAIL, 'Security Alert: audit_logs is append-only and cannot be updated.');
END;

-- Prevent any DELETE on audit_logs table
CREATE TRIGGER IF NOT EXISTS prevent_audit_log_delete
BEFORE DELETE ON audit_logs
BEGIN
    SELECT RAISE(FAIL, 'Security Alert: audit_logs is append-only and cannot be deleted.');
END;

-- 4. Indexes for Hash Verification and Expiration
CREATE INDEX IF NOT EXISTS idx_audit_logs_entry_hash ON audit_logs(entry_hash);
CREATE INDEX IF NOT EXISTS idx_hitl_approvals_expires_at ON hitl_approvals(expires_at);
