-- Rollback Migration: Drop chat sessions and messages tables
-- Description: Remove chat persistence tables (use only if needed to revert)
-- Date: 2025-10-09

-- Drop trigger first
DROP TRIGGER IF EXISTS trigger_update_chat_session_timestamp ON messages;

-- Drop function
DROP FUNCTION IF EXISTS update_chat_session_timestamp();

-- Drop tables (cascade will remove foreign keys)
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS chat_sessions CASCADE;

-- Note: This does not remove the uuid-ossp extension
-- as it might be used by other tables

SELECT 'Rollback completed: chat tables removed' AS status;
