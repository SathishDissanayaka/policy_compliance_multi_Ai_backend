# import google.generativeai as genai
from utils.pdf_parser import extract_text_from_pdf
from db.connection import get_db
import os
import uuid
import nltk
nltk.download('punkt')
from nltk.tokenize import sent_tokenize
from google import genai

class DocumentProcessor:
    def __init__(self):
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



    def process(self, file_path):
        try:
            # 1. Extract text
            text = extract_text_from_pdf(file_path)
            print(f"Length of text in characters: {len(text)}")
            if not text.strip():
                return {"agent": "DocumentProcessor", "status": "error", "result": "No text found in document"}
            
            chunks = self.chunk_text(text)
            
            # 3. Save to pgvector
            conn = get_db()
            cur = conn.cursor()
            i=0

            for chunk in chunks:
                i=i+1
                clean_chunk = chunk.replace("\x00", "")

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

                # Generate unique doc_id
                doc_id = str(uuid.uuid4())

                # Insert into DB
                cur.execute(
                    "INSERT INTO documents (id, content, embedding) VALUES (%s, %s, %s)",
                    (doc_id, clean_chunk, embedding)
                )
                print(f"Inserted chunk {i}/{len(chunks)}")


            conn.commit()
            cur.close()
            conn.close()

            return {
                "agent": "DocumentProcessor",
                "status": "success",
                "result": f"Document processed into {len(chunks)} chunks and saved"
            }

        except Exception as e:
            return {"agent": "DocumentProcessor", "status": "error", "result": str(e)}
