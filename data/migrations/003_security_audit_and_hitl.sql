-- Migration 003: Immutable Security Audit Logging & Persistent HITL Approvals
-- MY PERSONAL AI Phase 4

-- 1. Security Audit Logs Table (Append-only immutable record)
CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,                       -- UUID v4
    user_id TEXT DEFAULT NULL,                 -- User who initiated (or NULL for unauthenticated/system)
    event_type TEXT NOT NULL,                  -- 'AUTH_LOGIN', 'AUTH_REGISTER', 'AUTH_FAILED', 'SANDBOX_TRAVERSAL_BLOCKED', 'HITL_ACTION', 'TOOL_EXEC'
    action TEXT NOT NULL,                      -- Specific action name
    resource TEXT DEFAULT NULL,                -- Target resource (path, endpoint, table, user)
    status TEXT NOT NULL DEFAULT 'SUCCESS',    -- 'SUCCESS', 'DENIED', 'BLOCKED', 'ERROR'
    severity TEXT NOT NULL DEFAULT 'INFO',     -- 'INFO', 'WARNING', 'HIGH', 'CRITICAL'
    ip_address TEXT DEFAULT '127.0.0.1',       -- Client IP (strictly local)
    details_json TEXT DEFAULT '{}',            -- Parameter details, metadata, error message
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- 2. Human-in-the-Loop (HITL) Approvals Table
CREATE TABLE IF NOT EXISTS hitl_approvals (
    id TEXT PRIMARY KEY,                       -- UUID v4
    user_id TEXT NOT NULL,                     -- Target user
    conversation_id TEXT DEFAULT NULL,
    agent_name TEXT NOT NULL,                  -- Originating agent ('cybersec_agent', 'coding_agent', etc.)
    action TEXT NOT NULL,                      -- Action requiring approval
    reason TEXT NOT NULL,                      -- Detailed security or safety rationale
    risk_level TEXT NOT NULL DEFAULT 'HIGH',   -- 'MEDIUM', 'HIGH', 'CRITICAL'
    status TEXT NOT NULL DEFAULT 'PENDING',    -- 'PENDING', 'APPROVED', 'DENIED'
    metadata_json TEXT DEFAULT '{}',           -- Code payload, parameters, AST findings
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP DEFAULT NULL,
    resolved_by TEXT DEFAULT NULL,             -- User ID who approved/denied
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL
);

-- Performance & Query Indexes
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_event_type ON audit_logs(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_hitl_approvals_user_id ON hitl_approvals(user_id);
CREATE INDEX IF NOT EXISTS idx_hitl_approvals_status ON hitl_approvals(status);
