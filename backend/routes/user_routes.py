from flask import Blueprint, jsonify, g
from flask import request, jsonify
from middleware.auth import require_auth

from utils.supabase_client import supabase


user_bp = Blueprint("user", __name__)


@user_bp.route("/subscrition", methods=["POST"])
def create_subscription():
    data = request.get_json() or {}
    print(f"Subscription request body: {data}")

    user_id = data.get("userId") or data.get("user_id")
    plan = data.get("plan")
    status = "Pending"

    # Basic validation
    if not user_id or not plan:
        return jsonify({"error": "Missing required fields: userId and plan"}), 400

    if status not in ("Pending", "Approved"):
        return jsonify({"error": "Invalid status. Must be 'Pending' or 'Approved'"}), 400

    try:
        # Check if user already has a subscription
        existing_sub = (
            supabase.table("subscriptions")
            .select("id")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if hasattr(existing_sub, "data") and existing_sub.data:
            # Update existing subscription
            record = {"plan": plan}
            resp = (
                supabase.table("subscriptions")
                .update(record)
                .eq("id", existing_sub.data[0]["id"])
                .execute()
            )
        else:
            # Create new subscription
            record = {
                "user_id": user_id,
                "plan": plan,
                "status": status,
            }
            resp = supabase.table("subscriptions").insert(record).execute()

        # Handle response
        if hasattr(resp, "error") and resp.error:
            return jsonify({"error": str(resp.error)}), 500

        data_out = None
        if hasattr(resp, "data"):
            data_out = resp.data
        elif isinstance(resp, dict):
            data_out = resp.get("data")

        return jsonify({"status": "success", "data": data_out}), 201

    except Exception as e:
        print(f"Error handling subscription: {e}")
        return jsonify({"error": str(e)}), 500

    try:
        # Insert into Supabase. Assumes a table named `subscriptions` exists.
        resp = supabase.table("subscriptions").insert(record).execute()

        # supabase client returns an object with `data` and `error` attributes
        if hasattr(resp, "error") and resp.error:
            return jsonify({"error": str(resp.error)}), 500

        # Some client versions return a dict-like response
        data_out = None
        if hasattr(resp, "data"):
            data_out = resp.data
        elif isinstance(resp, dict):
            data_out = resp.get("data")

        return jsonify({"status": "success", "data": data_out}), 201

    except Exception as e:
        print(f"Error inserting subscription: {e}")
        return jsonify({"error": str(e)}), 500


@user_bp.route("/subscrition/user/", methods=["GET"])
@require_auth
def get_subscriptions_by_user():
    """Return subscriptions for a given user_id.

    Returns a list (possibly empty) of subscription records for the user.
    """
    try:
        user_id = getattr(g, "user_id", None)
        print(user_id)
        resp = (
            supabase.table("subscriptions")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )

        if hasattr(resp, "error") and resp.error:
            return jsonify({"error": str(resp.error)}), 500

        data_out = None
        if hasattr(resp, "data"):
            data_out = resp.data
        elif isinstance(resp, dict):
            data_out = resp.get("data")

        return jsonify({"status": "success", "data": data_out or []}), 200

    except Exception as e:
        print(f"Error fetching subscriptions for user {user_id}: {e}")
        return jsonify({"error": str(e)}), 500


@user_bp.route("/subscrition/<subscription_id>/status", methods=["PATCH"])
def update_subscription_status(subscription_id):
    """Update the status of a subscription by subscription id.

    Expected JSON body: { "status": "Pending" | "Approved" }
    """
    data = request.get_json() or {}
    status = data.get("status")

    if not status or status not in ("Pending", "Approved"):
        return jsonify({"error": "Invalid or missing status. Must be 'Pending' or 'Approved'"}), 400

    try:
        resp = (
            supabase.table("subscriptions")
            .update({"status": status})
            .eq("id", subscription_id)
            .execute()
        )

        if hasattr(resp, "error") and resp.error:
            return jsonify({"error": str(resp.error)}), 500

        data_out = None
        if hasattr(resp, "data"):
            data_out = resp.data
        elif isinstance(resp, dict):
            data_out = resp.get("data")

        # If no rows were updated, return 404
        if not data_out:
            return jsonify({"status": "not_found", "message": "Subscription not found"}), 404

        return jsonify({"status": "success", "data": data_out}), 200

    except Exception as e:
        print(f"Error updating subscription {subscription_id}: {e}")
        return jsonify({"error": str(e)}), 500


@user_bp.route("/subscrition/user/<user_id>/status", methods=["PATCH"])
def update_subscription_status_by_user(user_id):
    """Update the most recent subscription status for a user identified by user_id.

    Expected JSON body: { "status": "Pending" | "Approved" }
    This route will find the latest subscription (by created_at) for the user and update it.
    """
    data = request.get_json() or {}
    status = data.get("status")

    if not status or status not in ("Pending", "Approved"):
        return jsonify({"error": "Invalid or missing status. Must be 'Pending' or 'Approved'"}), 400

    try:
        # Find the most recent subscription for the user
        sel = (
            supabase.table("subscriptions")
            .select("id, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if hasattr(sel, "error") and sel.error:
            return jsonify({"error": str(sel.error)}), 500

        sel_data = None
        if hasattr(sel, "data"):
            sel_data = sel.data
        elif isinstance(sel, dict):
            sel_data = sel.get("data")

        if not sel_data:
            return jsonify({"status": "not_found", "message": "No subscription found for user"}), 404

        subscription_id = sel_data[0].get("id") if isinstance(sel_data, list) and sel_data else None
        if not subscription_id:
            return jsonify({"status": "not_found", "message": "No subscription id found for user"}), 404

        # Update that subscription by id
        resp = (
            supabase.table("subscriptions")
            .update({"status": status})
            .eq("id", subscription_id)
            .execute()
        )

        if hasattr(resp, "error") and resp.error:
            return jsonify({"error": str(resp.error)}), 500

        data_out = None
        if hasattr(resp, "data"):
            data_out = resp.data
        elif isinstance(resp, dict):
            data_out = resp.get("data")

        if not data_out:
            return jsonify({"status": "not_found", "message": "Subscription not found when updating"}), 404

        return jsonify({"status": "success", "data": data_out}), 200

    except Exception as e:
        print(f"Error updating subscription for user {user_id}: {e}")
        return jsonify({"error": str(e)}), 500
    

@user_bp.route("/role", methods=["GET", "OPTIONS"])
@require_auth
def get_user_role():
    user_id = getattr(g, "user_id", None)
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200  # Handles preflight

    try:
        resp = (
            supabase.table("new_profiles")
            .select("role")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )

        if hasattr(resp, "error") and resp.error:
            return jsonify({"error": str(resp.error)}), 500

        data_out = getattr(resp, "data", None) or resp.get("data", None)
        if not data_out:
            return jsonify({"status": "not_found", "message": "User not found"}), 404

        role = data_out[0].get("role") if isinstance(data_out, list) and data_out else None
        return jsonify({"status": "success", "role": role}), 200

    except Exception as e:
        print(f"Error fetching role for user {user_id}: {e}")
        return jsonify({"error": str(e)}), 500

@user_bp.route("/admin/create-user", methods=["POST"])
def create_user():
    print("Creating user...")
    data = request.get_json()
    admin_id = data.get("admin_id")
    email = data.get("email")
    password = data.get("password")

    # Create user in Supabase Auth (Admin API)
    response = supabase.auth.admin.create_user({
        "email": email,
        "password": password,
        "email_confirm": False
    })

    user = response.user
    if not user:
        return jsonify({"error": "Failed to create user"}), 400

    user_id = user.id

    # Insert into profiles table manually with admin_id
    supabase.table("new_profiles").update({
        "created_by": admin_id,
        "role": "employee"
    }).eq("id", user_id).execute()

    return jsonify({
        "message": "Employee account created successfully",
        "user_id": user_id
    }), 201
