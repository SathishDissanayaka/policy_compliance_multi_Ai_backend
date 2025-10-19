# import google.generativeai as genai
from db.connection import get_db
import os
from google import genai

class PolicyAnalyzeRetriever:
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = "gemini-embedding-001"

    def retrieve_for_embeddings(self, embeddings, safe_session_id, top_k=1):
        print(f"Retrieving chunks for multiple embeddings in temp_retriever.")
        try:
            conn = get_db()
            cur = conn.cursor()

            all_results = {}

            for idx, embedding in enumerate(embeddings):
                # Ensure float list
                embedding = [float(x) for x in embedding]

                query = f"""
                    SELECT id, content, embedding <=> %s::vector AS distance
                    FROM documents
                    ORDER BY distance
                    LIMIT %s
                """
                cur.execute(query, (embedding, top_k))
                rows = cur.fetchall()

                chunks = [
                    {"id": r[0], "content": r[1], "distance": r[2]}
                    for r in rows
                ]
                all_results[idx] = chunks

            cur.close()
            conn.close()

            return {"status": "success", "results": all_results}

        except Exception as e:
            return {"status": "error", "message": str(e)}
