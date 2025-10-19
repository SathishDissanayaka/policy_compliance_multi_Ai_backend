import google.generativeai as genai
from dotenv import load_dotenv
load_dotenv()
import os
# Configure Gemini API key
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

def get_text_embedding(text: str) -> list:
    """
    Get embedding for a given text using Gemini API
    """
    response = genai.embed_content(
        model="models/embedding-001",  # correct embedding model
        content=text
    )
    return response["embedding"]