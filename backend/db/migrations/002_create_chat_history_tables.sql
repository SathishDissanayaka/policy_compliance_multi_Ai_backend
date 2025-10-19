-- Migration: Create chat history tables (renamed to avoid conflicts)
-- Description: Add support for persistent chat history with user ownership
-- Date: 2025-10-09
-- Note: Using chat_history_sessions and chat_history_messages to avoid conflicts

-- Create chat_history_sessions table
CREATE TABLE IF NOT EXISTS chat_history_sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    title VARCHAR(255) DEFAULT 'New Chat',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index for user sessions lookup
CREATE INDEX IF NOT EXISTS idx_chat_history_sessions_user_id ON chat_history_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_history_sessions_updated_at ON chat_history_sessions(updated_at DESC);

-- Create chat_history_messages table
-- Note: message IDs will be generated in Python code
CREATE TABLE IF NOT EXISTS chat_history_messages (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Foreign key to ensure message belongs to valid session
    CONSTRAINT fk_chat_history_messages_session 
        FOREIGN KEY (session_id) 
        REFERENCES chat_history_sessions(id) 
        ON DELETE CASCADE
);

-- Create indexes for fast message retrieval
CREATE INDEX IF NOT EXISTS idx_chat_history_messages_session_id ON chat_history_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_chat_history_messages_created_at ON chat_history_messages(session_id, created_at);

-- Create function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_chat_history_session_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE chat_history_sessions 
    SET updated_at = NOW() 
    WHERE id = NEW.session_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to update session timestamp when message is added
DROP TRIGGER IF EXISTS trigger_update_chat_history_session_timestamp ON chat_history_messages;
CREATE TRIGGER trigger_update_chat_history_session_timestamp
    AFTER INSERT ON chat_history_messages
    FOR EACH ROW
    EXECUTE FUNCTION update_chat_history_session_timestamp();

-- Add comments for documentation
COMMENT ON TABLE chat_history_sessions IS 'Stores chat session metadata with user ownership for policy compliance chat';
COMMENT ON TABLE chat_history_messages IS 'Stores individual messages within chat sessions for policy compliance chat';
COMMENT ON COLUMN chat_history_sessions.user_id IS 'User ID from JWT token (Supabase auth.users.id)';
COMMENT ON COLUMN chat_history_messages.role IS 'Message sender: user, assistant, or system';
COMMENT ON COLUMN chat_history_messages.metadata IS 'Additional metadata like document_url, thinking_steps, etc.';
