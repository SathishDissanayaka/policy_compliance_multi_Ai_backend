from flask import Blueprint, jsonify, g
from middleware.auth import require_auth
from db.repositories.chat_repository import ChatRepository


chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/sessions", methods=["GET"])
@require_auth
def get_sessions():
    """Return the authenticated user's chat sessions (most recent first)."""
    user_id = getattr(g, "user_id", None)
    repo = ChatRepository()
    sessions = repo.get_user_sessions(user_id)
    return jsonify({"sessions": sessions})


@chat_bp.route("/sessions/<session_id>/messages", methods=["GET"])
@require_auth
def get_session_messages(session_id):
    """Return messages for a session after verifying ownership."""
    user_id = getattr(g, "user_id", None)
    repo = ChatRepository()

    session = repo.get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    if session.get("user_id") != user_id:
        return jsonify({"error": "Forbidden: session does not belong to user"}), 403

    messages = repo.get_messages(session_id)
    return jsonify({"session": session, "messages": messages})


@chat_bp.route("/sessions/<session_id>", methods=["DELETE"])
@require_auth
def delete_session(session_id):
    """Delete a session (and cascade delete messages) after verifying ownership."""
    user_id = getattr(g, "user_id", None)
    repo = ChatRepository()

    session = repo.get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    if session.get("user_id") != user_id:
        return jsonify({"error": "Forbidden: session does not belong to user"}), 403

    repo.delete_session(session_id)
    return jsonify({"status": "deleted", "session_id": session_id})





