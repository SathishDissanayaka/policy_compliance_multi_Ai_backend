import jwt
import os
from dotenv import load_dotenv
from flask import request, jsonify

load_dotenv()

SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")

def verify_jwt(token):
    try:
        decoded = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,   # HS256 uses symmetric key
            algorithms=["HS256"],
            audience="authenticated"
        )
        return decoded
    except Exception as e:
        print("JWT verification failed:", e)
        return None