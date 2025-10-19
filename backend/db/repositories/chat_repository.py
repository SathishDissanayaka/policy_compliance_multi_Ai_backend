"""
Chat Repository
---------------
Handles all database operations for chat sessions and messages.
Provides CRUD operations with proper error handling and type safety.
"""

import json
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime
from db.connection import get_db


class ChatRepository:
    """Repository for chat session and message persistence."""
    
    def __init__(self):
        """Initialize the chat repository."""
        pass
    
    def get_or_create_session(
        self, 
        session_id: str, 
        user_id: str, 
        title: str = "New Chat"
    ) -> Dict[str, Any]:
        """
        Get existing session or create new one with frontend-provided ID.
        
        Args:
            session_id: UUID string from frontend
            user_id: User ID from JWT token
            title: Session title (default: "New Chat")
            
        Returns:
            Dict with session data (id, user_id, title, created_at, updated_at)
        """
        session = self.get_session(session_id)
        
        if not session:
            # Create new session with frontend's UUID
            session = self.create_session(session_id, user_id, title)
        
        return session
    
    def create_session(
        self, 
        session_id: str, 
        user_id: str, 
        title: str = "New Chat"
    ) -> Dict[str, Any]:
        """
        Create new chat session with specific ID.
        
        Args:
            session_id: UUID string (frontend-generated)
            user_id: User ID from JWT token
            title: Session title
            
        Returns:
            Dict with created session data
        """
        conn = get_db()
        cursor = conn.cursor()
        
        try:
            query = """
                INSERT INTO chat_history_sessions (id, user_id, title, created_at, updated_at)
                VALUES (%s, %s, %s, NOW(), NOW())
                RETURNING id, user_id, title, created_at, updated_at
            """
            cursor.execute(query, (session_id, user_id, title))
            result = cursor.fetchone()
            conn.commit()
            
            if result:
                return {
                    'id': str(result[0]),
                    'user_id': str(result[1]),
                    'title': result[2],
                    'created_at': result[3].isoformat() if result[3] else None,
                    'updated_at': result[4].isoformat() if result[4] else None
                }
            return None
            
        except Exception as e:
            conn.rollback()
            raise Exception(f"Failed to create session: {str(e)}")
        finally:
            cursor.close()
            conn.close()
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session by ID.
        
        Args:
            session_id: Session UUID string
            
        Returns:
            Dict with session data or None if not found
        """
        conn = get_db()
        cursor = conn.cursor()
        
        try:
            query = """
                SELECT id, user_id, title, created_at, updated_at
                FROM chat_history_sessions
                WHERE id = %s
            """
            cursor.execute(query, (session_id,))
            result = cursor.fetchone()
            
            if result:
                return {
                    'id': str(result[0]),
                    'user_id': str(result[1]),
                    'title': result[2],
                    'created_at': result[3].isoformat() if result[3] else None,
                    'updated_at': result[4].isoformat() if result[4] else None
                }
            return None
            
        except Exception as e:
            raise Exception(f"Failed to get session: {str(e)}")
        finally:
            cursor.close()
            conn.close()
    
    def get_user_sessions(
        self, 
        user_id: str, 
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get all sessions for a user, ordered by most recent.
        
        Args:
            user_id: User ID from JWT token
            limit: Maximum number of sessions to return (default: 50)
            
        Returns:
            List of session dicts
        """
        conn = get_db()
        cursor = conn.cursor()
        
        try:
            query = """
                SELECT id, user_id, title, created_at, updated_at
                FROM chat_history_sessions
                WHERE user_id = %s
                ORDER BY updated_at DESC
                LIMIT %s
            """
            cursor.execute(query, (user_id, limit))
            results = cursor.fetchall()
            
            sessions = []
            for result in results:
                sessions.append({
                    'id': str(result[0]),
                    'user_id': str(result[1]),
                    'title': result[2],
                    'created_at': result[3].isoformat() if result[3] else None,
                    'updated_at': result[4].isoformat() if result[4] else None
                })
            
            return sessions
            
        except Exception as e:
            raise Exception(f"Failed to get user sessions: {str(e)}")
        finally:
            cursor.close()
            conn.close()
    
    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Save a message to a session.
        
        Args:
            session_id: Session UUID string
            role: Message role ('user', 'assistant', or 'system')
            content: Message content
            metadata: Optional metadata (document_url, thinking_steps, etc.)
            
        Returns:
            Dict with created message data
        """
        conn = get_db()
        cursor = conn.cursor()
        
        try:
            message_id = str(uuid.uuid4())
            
            # Convert metadata to JSON string for PostgreSQL JSONB column
            # If metadata is None or empty dict, store NULL
            if metadata:
                metadata_json = json.dumps(metadata)
            else:
                metadata_json = None
            
            query = """
                INSERT INTO chat_history_messages (id, session_id, role, content, metadata, created_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, NOW())
                RETURNING id, session_id, role, content, metadata, created_at
            """
            cursor.execute(query, (message_id, session_id, role, content, metadata_json))
            result = cursor.fetchone()
            conn.commit()
            
            if result:
                # psycopg2 returns JSONB as dict, no need to parse
                return {
                    'id': str(result[0]),
                    'session_id': str(result[1]),
                    'role': result[2],
                    'content': result[3],
                    'metadata': result[4] if result[4] else None,
                    'created_at': result[5].isoformat() if result[5] else None
                }
            return None
            
        except Exception as e:
            conn.rollback()
            raise Exception(f"Failed to save message: {str(e)}")
        finally:
            cursor.close()
            conn.close()
    
    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get all messages for a session, ordered chronologically.
        
        Args:
            session_id: Session UUID string
            
        Returns:
            List of message dicts
        """
        conn = get_db()
        cursor = conn.cursor()
        
        try:
            query = """
                SELECT id, session_id, role, content, metadata, created_at
                FROM chat_history_messages
                WHERE session_id = %s
                ORDER BY created_at ASC
            """
            cursor.execute(query, (session_id,))
            results = cursor.fetchall()
            
            messages = []
            for result in results:
                # psycopg2 returns JSONB as dict, no need to parse
                messages.append({
                    'id': str(result[0]),
                    'session_id': str(result[1]),
                    'role': result[2],
                    'content': result[3],
                    'metadata': result[4] if result[4] else None,
                    'created_at': result[5].isoformat() if result[5] else None
                })
            
            return messages
            
        except Exception as e:
            raise Exception(f"Failed to get messages: {str(e)}")
        finally:
            cursor.close()
            conn.close()
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete a session (cascade deletes messages).
        
        Args:
            session_id: Session UUID string
            
        Returns:
            True if successful
        """
        conn = get_db()
        cursor = conn.cursor()
        
        try:
            query = "DELETE FROM chat_history_sessions WHERE id = %s"
            cursor.execute(query, (session_id,))
            conn.commit()
            return True
            
        except Exception as e:
            conn.rollback()
            raise Exception(f"Failed to delete session: {str(e)}")
        finally:
            cursor.close()
            conn.close()
    
    def update_session_title(self, session_id: str, title: str) -> bool:
        """
        Update session title.
        
        Args:
            session_id: Session UUID string
            title: New title
            
        Returns:
            True if successful
        """
        conn = get_db()
        cursor = conn.cursor()
        
        try:
            query = """
                UPDATE chat_history_sessions 
                SET title = %s, updated_at = NOW() 
                WHERE id = %s
            """
            cursor.execute(query, (title, session_id))
            conn.commit()
            return True
            
        except Exception as e:
            conn.rollback()
            raise Exception(f"Failed to update session title: {str(e)}")
        finally:
            cursor.close()
            conn.close()
