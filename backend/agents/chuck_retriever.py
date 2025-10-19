# import google.generativeai as genai
from db.connection import get_db
import os
from google import genai

class Retriever:
    def __init__(self):
        # Initialize client using API key from environment
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = "gemini-embedding-001"

    def retrieve_chunks(self, question, top_k=5):
        print(f"Retrieved Question inside the chunk retriever: {question}")
        """
        Returns top-k most relevant chunks from the database for a question.
        """
        try:
            # 1. Create embedding for the question
            result = self.client.models.embed_content(
                model=self.model,
                contents=[question]  # must be a list
            )

            # Extract the embedding vector (first item because we passed one text)
            question_embedding = result.embeddings[0].values

            print(f"Question Embedding (first 5 dims): {question_embedding[:5]}...")

            # Ensure it's a float list
            question_embedding = [float(x) for x in question_embedding]

            # 2. Query pgvector
            conn = get_db()
            cur = conn.cursor()

            query = """
                SELECT id, content, embedding <=> %s::vector AS distance
                FROM documents
                ORDER BY distance
                LIMIT %s
            """
            cur.execute(query, (question_embedding, top_k))
            results = cur.fetchall()
            cur.close()
            conn.close()

            # 3. Format results
            chunks = [{"id": r[0], "content": r[1], "distance": r[2]} for r in results]
            print(f"Retrieved {len(chunks)} chunks from DB.")
            return {"status": "success", "chunks": chunks}

        except Exception as e:
            return {"status": "error", "message": str(e)}
