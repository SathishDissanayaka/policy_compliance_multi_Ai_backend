# import google.generativeai as genai
from utils.pdf_parser import extract_text_from_pdf
from db.connection import get_db
import os
import uuid
import nltk
from google import genai
# Download punkt data if not already downloaded
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

nltk.download('punkt_tab')
from nltk.tokenize import sent_tokenize
from dotenv import load_dotenv
load_dotenv()

class DocumentProcessorTemp:
    def __init__(self):
        print(f"Initializing DocumentProcessorTemp")
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = "gemini-embedding-001"

    def chunk_text(self, text, sentences_per_chunk=15, overlap=3):
        text = ' '.join(text.split())
        sentences = sent_tokenize(text)
        chunks = []
        start = 0

        while start < len(sentences):
            end = start + sentences_per_chunk
            chunk = " ".join(sentences[start:end])
            chunks.append(chunk)
            start += sentences_per_chunk - overlap  # move with overlap

        return chunks



    def process(self, file_path, session_id: str):
        try:
            print(f"Processing document for session inside attached_document_processor")
            print(f"File path: {file_path}, Session ID: {session_id}")
            # 1. Extract text
            text = extract_text_from_pdf(file_path)
            print(f"Length of text in characters: {len(text)}")
            if not text.strip():
                return {"agent": "DocumentProcessor", "status": "error", "result": "No text found in PDF"}
            
            chunks = self.chunk_text(text)
            print(f"Total chunks created: {len(chunks)}")
            # 3. Save to pgvector
            conn = get_db()
            cur = conn.cursor()
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS temp_documents_{session_id} (
                    id UUID PRIMARY KEY,
                    content TEXT,
                    embedding vector(3072)
                )
            """)
            conn.commit()
            i=0

            for chunk in chunks:
                i=i+1
                clean_chunk = chunk.replace("\x00", "")
                print(f"Processing chunk {i}/{len(chunks)}")

                try:
                    # Generate embedding using official API
                    result = self.client.models.embed_content(
                        model=self.model,
                        contents=[clean_chunk]  # must be a list
                    )

                    # Extract embedding
                    embedding = result.embeddings[0].values
                    embedding = [float(x) for x in embedding]

                except Exception as e:
                    return {
                        "agent": "DocumentProcessor",
                        "status": "error",
                        "result": str(e)
                    }


                doc_id = str(uuid.uuid4())
                cur.execute(
                    f"INSERT INTO temp_documents_{session_id} (id, content, embedding) VALUES (%s, %s, %s)",
                    (doc_id, clean_chunk, embedding)
                )
                print(f"Inserted chunk {i}/{len(chunks)}")


            conn.commit()
            cur.close()
            conn.close()

            return {
                "agent": "TempDocumentProcessor",
                "status": "success",
                "result": f"Document processed into {len(chunks)} chunks and saved to temp_documents table"
            }

        except Exception as e:
            return {"agent": "TempDocumentProcessor", "status": "error", "result": str(e)}