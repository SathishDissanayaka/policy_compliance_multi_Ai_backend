"""
Check what tables exist in the database
"""

from db.connection import get_db

def check_tables():
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Check if tables exist
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('chat_sessions', 'messages')
            ORDER BY table_name;
        """)
        tables = cursor.fetchall()
        
        print("Existing tables:")
        if tables:
            for (table_name,) in tables:
                print(f"  - {table_name}")
                
                # Show columns
                cursor.execute("""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = %s
                    ORDER BY ordinal_position;
                """, (table_name,))
                columns = cursor.fetchall()
                for col, dtype in columns:
                    print(f"      {col}: {dtype}")
        else:
            print("  No chat tables found")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_tables()
