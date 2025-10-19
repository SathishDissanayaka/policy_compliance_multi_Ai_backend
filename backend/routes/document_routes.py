from flask import Blueprint, request, jsonify, url_for
from agents.document_processor import DocumentProcessor
import os
import tempfile
import requests
from agents.policy_analyze_document_processor import AnalyzeDocumentProcessorTemp
from agents.policy_analyze_chunk_retriever import PolicyAnalyzeRetriever
from agents.international_policy_retriever import InternationalPolicyRetriever
from google import genai
from middleware.auth import require_auth
from agents.international_policy_processor import InternationalPolicyProcessor
from urllib.parse import urlparse

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
document_bp = Blueprint("documents", __name__)
processor = DocumentProcessor()
doc_processor = AnalyzeDocumentProcessorTemp()
policyAnalyzeRetriever = PolicyAnalyzeRetriever()
internationalPolicyRetriever = InternationalPolicyRetriever()
int_processor = InternationalPolicyProcessor()

@document_bp.route("/upload", methods=["POST"])
@require_auth
def upload_document():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files["file"]
# Ensure uploads directory exists
    upload_dir = "./uploads"
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, file.filename)
    file.save(file_path)

    result = processor.process(file_path)
    return jsonify(result)

@document_bp.route("/analyze", methods=["POST"])
@require_auth
def analyze_document():
    data = request.json
    document_url = data.get("document_url")
    session_id = data.get("session_id")
    selected_policies = data.get("selected_policies", [])
    safe_session_id = session_id.replace("-", "_")

    if not document_url:
        return jsonify({"error": "No document URL provided"}), 400

    # Derive a friendly analyzed document name from the URL (best-effort)
    try:
        parsed = urlparse(document_url)
        analyzed_document_name = os.path.basename(parsed.path) or "document.pdf"
    except Exception:
        analyzed_document_name = "document.pdf"

    # Download file
    res = requests.get(document_url).content
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(res)
        tmp_file_path = tmp.name

    try:
        # Process into chunks + embeddings
        vector_store = doc_processor.process(tmp_file_path, safe_session_id)

        if not isinstance(vector_store, dict):
            return jsonify({
                "agent": "AnalyzeDocumentProcessor",
                "status": "error",
                "result": "Unexpected response from document processor"
            }), 500

        if vector_store.get("status") != "success":
            return jsonify({
                "agent": vector_store.get("agent", "AnalyzeDocumentProcessor"),
                "status": vector_store.get("status", "error"),
                "result": vector_store.get("result", "Document processing failed")
            }), 400

        chunk_embeddings = vector_store.get("chunk_embeddings", [])
        if not chunk_embeddings:
            return jsonify({
                "agent": vector_store.get("agent", "AnalyzeDocumentProcessor"),
                "status": "error",
                "result": "No text extracted from document"
            }), 400

        retrieval_results = policyAnalyzeRetriever.retrieve_for_embeddings(
            [c["embedding"] for c in chunk_embeddings],
            safe_session_id,
            top_k=1
        )

        # Map back attached chunks to matching policies
        paired_contexts = []
        if retrieval_results["status"] == "success":
            for idx, matches in retrieval_results["results"].items():
                attached_chunk = chunk_embeddings[int(idx)]["chunk"]
                for match in matches:
                    # build a short snippet to keep API responses compact for the UI
                    full_text = match.get("content") or ""
                    snippet = full_text[:400]
                    # try to cut at last sentence end for nicer display
                    last_period = max(snippet.rfind('.'), snippet.rfind('!'), snippet.rfind('?'))
                    if last_period and last_period > 50:
                        snippet = snippet[: last_period + 1]

                    paired_contexts.append({
                        "attached_chunk": attached_chunk,
                        "matching_policy": full_text,
                        "paired_context_snippet": snippet,
                        "distance": match["distance"],
                        "policy_type": "company_policy",
                        # structured provenance
                        "policy_id": match.get("id"),
                        "source": {
                            "table": "documents",
                            "policy_id": match.get("id"),
                            "url": url_for(
                                "policies.get_company_policy",
                                policy_id=match.get("id"),
                                _external=True
                            ) if match.get("id") else None
                        },
                        "attached": {
                            "document_name": analyzed_document_name,
                            "document_url": document_url,
                            "chunk_index": int(idx)
                        }
                    })
                    
        # Process international policies if selected
        if selected_policies:
            document_embeddings = [c["embedding"] for c in chunk_embeddings]
            
            for policy in selected_policies:
                int_policy_results = internationalPolicyRetriever.retrieve_for_embeddings(
                    document_embeddings,
                    safe_session_id,
                    policy,
                    top_k=1
                )
                
                if int_policy_results["status"] == "success":
                    for idx, matches in int_policy_results["results"].items():
                        attached_chunk = chunk_embeddings[int(idx)]["chunk"]
                        for match in matches:
                            full_text = match.get("content") or ""
                            snippet = full_text[:400]
                            last_period = max(snippet.rfind('.'), snippet.rfind('!'), snippet.rfind('?'))
                            if last_period and last_period > 50:
                                snippet = snippet[: last_period + 1]

                            paired_contexts.append({
                                "attached_chunk": attached_chunk,
                                "matching_policy": full_text,
                                "paired_context_snippet": snippet,
                                "distance": match["distance"],
                                "policy_type": f"international_policy_{policy}",
                                # structured provenance
                                "policy": policy,
                                "policy_id": match.get("id"),
                                "source": {
                                    "table": "international_policy",
                                    "policy": policy,
                                    "policy_id": match.get("id"),
                                    "url": url_for(
                                        "policies.get_international_policy",
                                        policy=policy,
                                        policy_id=match.get("id"),
                                        _external=True
                                    ) if match.get("id") else None
                                },
                                "attached": {
                                    "document_name": analyzed_document_name,
                                    "document_url": document_url,
                                    "chunk_index": int(idx)
                                }
                            })

        print(f"Total paired contexts: {paired_contexts}")
        # Prompt Gemini
        prompt = f"""
        You are a compliance analyzer. Compare attached document clauses with both company policies and international regulations. 
        Identify violations, explain them, and return only a JSON array of objects in this format:

        [
          {{
            "type": "Violation",
            "title": "...",
            "description": "...",
            "severity": "high|medium|low",
            "policy_type": "..."  # either 'Company Policy' or 'International Policy - [policy_name]'
          }}
        ]

        Note that each paired context includes a policy_type field indicating whether it's a company policy or an international policy (like GDPR, HIPAA, etc).

        Here are the pairs of context:
        {paired_contexts}
        """

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        import json
        import re

        raw_text = response.text

        # Remove ```json or ``` code block if present
        cleaned_text = re.sub(r"^```json\s*|```$", "", raw_text.strip())

        try:
            violations = json.loads(cleaned_text)
        except json.JSONDecodeError:
            violations = {"error": "Failed to parse LLM response", "raw": raw_text}

        print("Violations found:", violations)
        # Return both violations and the paired_contexts so downstream services
        # (or the frontend) can forward the authoritative contexts to the
        # recommendations endpoint. This avoids having the recommender re-run
        # fuzzy matching against a fallback store.
        return jsonify({
            "violations": violations,
            "paired_contexts": paired_contexts
        })

    finally:
        os.remove(tmp_file_path)

@document_bp.route("/upload/international", methods=["POST"])
def upload_international_document():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files["file"]
# Ensure uploads directory exists
    upload_dir = "./uploads"
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, file.filename)
    file.save(file_path)

    result = int_processor.process(file_path)
    return jsonify(result)