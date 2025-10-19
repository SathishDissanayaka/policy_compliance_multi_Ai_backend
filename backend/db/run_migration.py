"""
Database Migration Runner
-------------------------
Run this script to apply database migrations for chat persistence.

Usage:
    python -m db.run_migration

This will:
1. Test database connection
2. Create chat_sessions and messages tables
3. Create necessary indexes and triggers
"""

import os
import sys
from pathlib import Path
from connection import get_db

def test_connection():
    """Test database connection before running migrations."""
    print("🔍 Testing database connection...")
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"✅ Connected to PostgreSQL: {version[:50]}...")
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def run_migration(migration_file: str):
    """Run a single migration file."""
    print(f"\n📄 Running migration: {migration_file}")
    
    try:
        # Read migration SQL
        migration_path = Path(__file__).parent / "migrations" / migration_file
        with open(migration_path, 'r') as f:
            sql = f.read()
        
        # Execute migration
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(sql)
        conn.commit()
        
        print(f"✅ Migration completed: {migration_file}")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

def verify_tables():
    """Verify that tables were created successfully."""
    print("\n🔍 Verifying tables...")
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Check chat_history_sessions table
        cursor.execute("""
            SELECT table_name, column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'chat_history_sessions'
            ORDER BY ordinal_position;
        """)
        sessions_columns = cursor.fetchall()
        
        if sessions_columns:
            print("\n✅ Table 'chat_history_sessions' created with columns:")
            for table, column, dtype in sessions_columns:
                print(f"   - {column}: {dtype}")
        else:
            print("❌ Table 'chat_history_sessions' not found")
            return False
        
        # Check chat_history_messages table
        cursor.execute("""
            SELECT table_name, column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'chat_history_messages'
            ORDER BY ordinal_position;
        """)
        messages_columns = cursor.fetchall()
        
        if messages_columns:
            print("\n✅ Table 'chat_history_messages' created with columns:")
            for table, column, dtype in messages_columns:
                print(f"   - {column}: {dtype}")
        else:
            print("❌ Table 'chat_history_messages' not found")
            return False
        
        # Check indexes
        cursor.execute("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename IN ('chat_history_sessions', 'chat_history_messages')
            ORDER BY indexname;
        """)
        indexes = cursor.fetchall()
        
        if indexes:
            print("\n✅ Indexes created:")
            for (idx_name,) in indexes:
                print(f"   - {idx_name}")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

def main():
    """Main migration runner."""
    print("=" * 60)
    print("🚀 Database Migration Runner")
    print("=" * 60)
    
    # Step 1: Test connection
    if not test_connection():
        print("\n❌ Migration aborted: Cannot connect to database")
        print("\nPlease check your .env file contains:")
        print("  - DB_NAME")
        print("  - DB_USER")
        print("  - DB_PASSWORD")
        print("  - DB_HOST")
        print("  - DB_PORT")
        sys.exit(1)
    
    # Step 2: Run migration
    if not run_migration("002_create_chat_history_tables.sql"):
        print("\n❌ Migration failed")
        sys.exit(1)
    
    # Step 3: Verify tables
    if not verify_tables():
        print("\n❌ Verification failed")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("🎉 Migration completed successfully!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Review the created tables in your database")
    print("  2. Proceed to Step 2: Create ChatRepository class")
    print()

if __name__ == "__main__":
    main()
