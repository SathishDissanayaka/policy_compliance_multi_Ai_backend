from flask import Blueprint, request, jsonify, Response, g
from orchestrator.orchestrator import get_orchestrator
from db.repositories.chat_repository import ChatRepository
from middleware.auth import require_auth
from dotenv import load_dotenv

load_dotenv()

query_bp = Blueprint("queries", __name__)


@query_bp.route("/analyze/stream", methods=["POST"])
@require_auth  # Add authentication - extracts user_id from JWT
def analyze_stream():
    """Stream events from the orchestrator graph as Server-Sent Events (SSE).

    This preserves the logic of the existing `/analyze` route but exposes
    intermediate events emitted by the graph's `astream_events` API so the
    client can render streaming updates.
    """
    print("=" * 80)
    print("[ROUTE] /analyze/stream endpoint called")
    print(f"[ROUTE] Authenticated User ID: {g.user_id}")
    print(f"[ROUTE] User Email: {g.user_email}")
    print("=" * 80)
    
    try:
        data = request.json
        session_id = data["session_id"]
        msg = data["message"]
        document_url = data.get("document_url")

        print(f"[ROUTE] Parsed request - Session: {session_id}, Message: {msg[:100]}...")
        if document_url:
            print(f"[ROUTE] Document URL provided: {document_url}")

        # Validate session ownership if session exists
        repo = ChatRepository()
        user_id = getattr(g, 'user_id', None)
        existing = repo.get_session(session_id)
        if existing and existing.get('user_id') != user_id:
            return jsonify({"error": "Forbidden: session does not belong to user"}), 403

        # Get orchestrator and create stream generator
        print(f"[ROUTE] Getting orchestrator...")
        orchestrator = get_orchestrator()
        print(f"[ROUTE] Creating stream generator via orchestrator...")
        stream_generator = orchestrator.create_stream_generator(session_id, msg, document_url, user_id)
        print(f"[ROUTE] Stream generator created, returning SSE response")

        # Return a Flask Response streaming SSE
        return Response(stream_generator, mimetype='text/event-stream')

    except Exception as e:
        print(f"[ROUTE] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
