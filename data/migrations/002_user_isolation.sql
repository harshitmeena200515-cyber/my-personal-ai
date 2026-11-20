-- Migration 002: User Data Isolation & Persistence
-- MY PERSONAL AI Phase 4B

-- 1. Conversations Table
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,                       -- UUID v4
    user_id TEXT NOT NULL,                     -- Owner user
    title TEXT NOT NULL DEFAULT 'New Conversation',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 2. Messages Table
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,                       -- UUID v4
    conversation_id TEXT NOT NULL,
    user_id TEXT NOT NULL,                     -- Explicit user ownership check
    role TEXT NOT NULL,                        -- 'user', 'assistant', 'system'
    content TEXT NOT NULL,
    reasoning TEXT DEFAULT NULL,               -- Thought/planning steps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 3. Tasks Table (User-specific autonomous task tracking)
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,                       -- UUID v4
    user_id TEXT NOT NULL,
    conversation_id TEXT DEFAULT NULL,
    goal TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',    -- 'pending', 'running', 'completed', 'failed'
    plan_json TEXT DEFAULT NULL,
    result_json TEXT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP DEFAULT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL
);

-- Performance & Isolation Indexes
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_conversation_id ON tasks(conversation_id);
