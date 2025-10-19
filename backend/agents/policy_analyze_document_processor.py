from utils.pdf_parser import extract_text_from_pdf
from db.connection import get_db
import os
import uuid
import nltk
from google import genai
from nltk.tokenize import sent_tokenize
from dotenv import load_dotenv

# Download punkt if missing
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
nltk.download('punkt_tab')

load_dotenv()

class AnalyzeDocumentProcessorTemp:
    def __init__(self):
        print("Initializing DocumentProcessorTemp")
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = "gemini-embedding-001"

    def chunk_text(self, text, sentences_per_chunk=10, overlap=2):
        """Split text into overlapping chunks of sentences."""
        text = ' '.join(text.split())
        sentences = sent_tokenize(text)
        chunks, start = [], 0

        while start < len(sentences):
            end = start + sentences_per_chunk
            chunk = " ".join(sentences[start:end])
            chunks.append(chunk)
            start += sentences_per_chunk - overlap

        return chunks

    def process(self, file_path, session_id: str):
        try:
            print(f"Processing document for session {session_id}")
            text = extract_text_from_pdf(file_path)
            print(f"Length of text: {len(text)} chars")

            if not text.strip():
                return {
                    "agent": "AnalyzeDocumentProcessor",
                    "status": "error",
                    "result": "No text found in document"
                }

            chunks = self.chunk_text(text)
            print(f"Total chunks created: {len(chunks)}")

            conn = get_db()
            cur = conn.cursor()
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS analyze_documents_{session_id} (
                    id UUID PRIMARY KEY,
                    content TEXT,
                    embedding vector(3072)
                )
            """)
            conn.commit()

            embeddings = []  # <-- collect embeddings here
            results = []     # <-- collect (chunk, embedding) pairs

            for i, chunk in enumerate(chunks, start=1):
                clean_chunk = chunk.replace("\x00", "")
                print(f"Processing chunk {i}/{len(chunks)}")

                try:
                    # Get embedding
                    result = self.client.models.embed_content(
                        model=self.model,
                        contents=[clean_chunk]
                    )
                    embedding = [float(x) for x in result.embeddings[0].values]

                    # Save to DB
                    doc_id = str(uuid.uuid4())
                    cur.execute(
                        f"INSERT INTO analyze_documents_{session_id} (id, content, embedding) VALUES (%s, %s, %s)",
                        (doc_id, clean_chunk, embedding)
                    )
                    embeddings.append(embedding)
                    results.append({"chunk": clean_chunk, "embedding": embedding})

                except Exception as e:
                    return {
                        "agent": "AnalyzeDocumentProcessor",
                        "status": "error",
                        "result": str(e)
                    }

            print(f"Inserted {len(chunks)} chunks into DB")
            conn.commit()
            cur.close()
            conn.close()

            return {
                "agent": "AnalyzeDocumentProcessor",
                "status": "success",
                "result": f"Document processed into {len(chunks)} chunks",
                "chunks": chunks,
                "embeddings": embeddings,
                "chunk_embeddings": results
            }

        except Exception as e:
            return {
                "agent": "AnalyzeDocumentProcessor",
                "status": "error",
                "result": str(e)
            }
