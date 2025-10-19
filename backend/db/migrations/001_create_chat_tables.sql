-- Migration: Create chat sessions and messages tables
-- Description: Add support for persistent chat history with user ownership
-- Date: 2025-10-09
-- Note: UUIDs will be generated in application code (Python), no extension needed

-- Create chat_sessions table
CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    title VARCHAR(255) DEFAULT 'New Chat',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Add index for fast user lookup
    CONSTRAINT chat_sessions_user_id_idx_temp UNIQUE (id, user_id)
);

-- Create index for user sessions lookup
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated_at ON chat_sessions(updated_at DESC);

-- Create messages table
-- Note: message IDs will be generated in Python code
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Foreign key to ensure message belongs to valid session
    CONSTRAINT fk_messages_session 
        FOREIGN KEY (session_id) 
        REFERENCES chat_sessions(id) 
        ON DELETE CASCADE
);

-- Create indexes for fast message retrieval
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(session_id, created_at);

-- Create function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_chat_session_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE chat_sessions 
    SET updated_at = NOW() 
    WHERE id = NEW.session_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to update session timestamp when message is added
DROP TRIGGER IF EXISTS trigger_update_chat_session_timestamp ON messages;
CREATE TRIGGER trigger_update_chat_session_timestamp
    AFTER INSERT ON messages
    FOR EACH ROW
    EXECUTE FUNCTION update_chat_session_timestamp();

-- Add comments for documentation
COMMENT ON TABLE chat_sessions IS 'Stores chat session metadata with user ownership';
COMMENT ON TABLE messages IS 'Stores individual messages within chat sessions';
COMMENT ON COLUMN chat_sessions.user_id IS 'User ID from JWT token (Supabase auth.users.id)';
COMMENT ON COLUMN messages.role IS 'Message sender: user, assistant, or system';
COMMENT ON COLUMN messages.metadata IS 'Additional metadata like document_url, thinking_steps, etc.';
