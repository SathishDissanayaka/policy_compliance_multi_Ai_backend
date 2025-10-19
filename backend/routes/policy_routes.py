from flask import Blueprint, jsonify, request
from middleware.auth import require_auth
from db.connection import get_db

policy_bp = Blueprint("policies", __name__)


@policy_bp.route("/company/<policy_id>", methods=["GET"])
@require_auth
def get_company_policy(policy_id):
    """Return a full company policy entry by ID."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, content FROM documents WHERE id = %s",
            (policy_id,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            return jsonify({"error": "Policy not found"}), 404

        return jsonify({
            "policy_id": row[0],
            "policy_type": "company_policy",
            "content": row[1]
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@policy_bp.route("/international/<policy>/<policy_id>", methods=["GET"])
@require_auth
def get_international_policy(policy, policy_id):
    """Return a full international policy entry by policy name + ID."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, policy, content FROM international_policy WHERE policy = %s AND id = %s",
            (policy, policy_id)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            return jsonify({"error": "Policy not found"}), 404

        return jsonify({
            "policy_id": row[0],
            "policy": row[1],
            "policy_type": f"international_policy_{row[1]}",
            "content": row[2]
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
