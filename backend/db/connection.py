import psycopg2
from psycopg2.extras import register_uuid
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def get_db():
    conn = psycopg2.connect(
        dbname=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "password"),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432")
    )
    return conn