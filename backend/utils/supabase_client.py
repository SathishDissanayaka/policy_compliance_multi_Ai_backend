import os
from dotenv import load_dotenv
from supabase import create_client, Client

# This loads your .env file automatically
load_dotenv()  

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

supabase: Client = create_client(url, key)

