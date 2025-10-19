from flask import Blueprint, request, jsonify
from agents.recommendation_agent import RecommendationAgent
from middleware.auth import require_auth
from utils.policy_contexts import get_policy_contexts
from utils.embeddings import get_text_embedding

recommendation_bp = Blueprint("recommendations", __name__)
recommendation_agent = RecommendationAgent()

@recommendation_bp.route("/generate", methods=["POST"])
@require_auth
def generate_recommendations():
    """
    Generate recommendations based on violation data
    
    Expected input:
    {
        "violations": [
            {
                "type": "Violation",
                "title": "...",
                "description": "...",
                "severity": "high|medium|low"
            }
        ],
        "session_id": "optional-session-id"
    }
    """
    try:
        print("Received recommendation request inside backend")
        data = request.json

        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        violations = data.get("violations", [])
        session_id = data.get("session_id")
        
        if not violations:
            return jsonify({
                "agent": "RecommendationAgent",
                "status": "success",
                "message": "No violations provided, no recommendations needed",
                "recommendations": [],
                "confidence": 1.0,
                "reasoning": "No compliance violations identified"
            })

        # Prefer paired contexts supplied in the request payload (authoritative)
        incoming_paired = data.get("paired_contexts")
        if incoming_paired and isinstance(incoming_paired, list):
            paired_contexts = incoming_paired
            print(f"Using {len(paired_contexts)} paired_contexts supplied in request payload")
        else:
            # Fetch paired policy contexts from Supabase as a fallback/cache
            paired_contexts = get_policy_contexts()
            print(f"Fetched {len(paired_contexts)} policy contexts from Supabase")

        # Attach relevant context to each violation using several heuristics:
        #  - exact policy_id match (with string normalization)
        #  - match by title/name fields (case-insensitive substring)
        def _safe_str(x):
            try:
                return str(x).strip()
            except Exception:
                return ""

        # Pre-index some searchable fields on contexts to speed matching
        # Include additional fields often returned by retrieval pipelines
        for ctx in paired_contexts:
            ctx["_searchable"] = " ".join(
                filter(None, [_safe_str(ctx.get(k)).lower() for k in (
                    "policy_title", "title", "name", "policy_name", "content", "context", "text", "description",
                    # fields observed in your data
                    "attached_chunk", "matching_policy", "policy_text", "body"
                )])
            )

        for violation in violations:
            # If the violation already includes attached contexts (e.g. from document analysis), keep them
            if violation.get("contexts"):
                print(f"Violation '{violation.get('title')}' already has {len(violation.get('contexts') or [])} context(s) attached; skipping matching")
                continue
            v_policy_id = violation.get("policy_id")
            v_title = _safe_str(violation.get("title")).lower()
            related_contexts = []

            # 1) Try exact policy_id match (normalize to string)
            if v_policy_id is not None:
                s_vid = _safe_str(v_policy_id)
                related_contexts = [c for c in paired_contexts if _safe_str(c.get("policy_id")) == s_vid]

            # 2) If none found, try substring/title matching against common fields
            if not related_contexts and v_title:
                related_contexts = [c for c in paired_contexts if v_title and v_title in (c.get("_searchable") or "")]

            # 3) Final fallback: any context whose searchable text appears in violation description
            if not related_contexts:
                v_desc = _safe_str(violation.get("description")).lower()
                if v_desc:
                    related_contexts = [c for c in paired_contexts if v_desc and v_desc in (c.get("_searchable") or "")]

            # 4) Lightweight token-overlap scoring fallback: pick contexts with the most token overlap
            if not related_contexts and (v_title or v_desc):
                tokens = set(((v_title or "") + " " + (v_desc or "")).split())
                scores = []
                for c in paired_contexts:
                    s = set((c.get("_searchable") or "").split())
                    overlap = len(tokens & s)
                    if overlap > 0:
                        scores.append((overlap, c))
                if scores:
                    scores.sort(key=lambda x: x[0], reverse=True)
                    # choose top-scoring context(s)
                    related_contexts = [scores[0][1]]

            # If multiple contexts, prefer the closest (smallest distance) first
            try:
                related_contexts.sort(key=lambda c: float(c.get("distance", 1e9)))
            except Exception:
                pass
            violation["contexts"] = related_contexts
            print(f"Violation '{violation.get('title')}' matched {len(related_contexts)} context(s)")

        # Generate recommendations with attached contexts
        result = recommendation_agent.generate_recommendations(violations)
        
        # Attach paired_context to each recommendation (defensive)
        if result.get("status") == "success":
            recommendations = result.get("recommendations", [])

            def extract_context_text(ctx: dict) -> str:
                """Return a readable text for a policy context row.

                We accept a few possible column names (content, context, text, description)
                to be robust against schema differences.
                """
                if not ctx or not isinstance(ctx, dict):
                    return ""
                # prefer a short snippet if available, then fall back to longer fields
                for key in ("paired_context_snippet", "matching_policy", "attached_chunk", "policy_text", "content", "context", "text", "description"):
                    if key in ctx and ctx.get(key):
                        return str(ctx.get(key))
                # Fallback to pretty-printing the whole row
                try:
                    return str(ctx)
                except Exception:
                    return ""

            for rec in recommendations:
                # Try to match the recommendation to its original violation.
                # The agent currently sets `violation_id` equal to the violation title.
                violation = next(
                    (v for v in violations if v.get("title") == rec.get("violation_id")),
                    None
                )

                paired_text = "No context available"

                # Prefer contexts attached directly to the matched violation
                if violation:
                    v_contexts = violation.get("contexts") or []
                    if v_contexts:
                        paired_text = extract_context_text(v_contexts[0])
                        # include meta for frontend if available
                        rec["paired_context_meta"] = {
                            "policy_type": v_contexts[0].get("policy_type"),
                            "distance": v_contexts[0].get("distance"),
                            "policy_id": v_contexts[0].get("policy_id"),
                            "source": v_contexts[0].get("source"),
                            "attached": v_contexts[0].get("attached"),
                        }

                # If not found, try to match using any policy_id referenced on the rec or violation
                if paired_text == "No context available":
                    # attempt policy_id from violation
                    policy_id = None
                    if violation:
                        policy_id = violation.get("policy_id")
                    # attempt policy_id from recommendation (if agent included it)
                    if not policy_id:
                        policy_id = rec.get("policy_id")

                    if policy_id:
                        related = [c for c in paired_contexts if c.get("policy_id") == policy_id]
                        if related:
                            paired_text = extract_context_text(related[0])
                            rec["paired_context_meta"] = {
                                "policy_type": related[0].get("policy_type"),
                                "distance": related[0].get("distance"),
                                "policy_id": related[0].get("policy_id"),
                                "source": related[0].get("source"),
                                "attached": related[0].get("attached"),
                            }

                # final fallback: if the recommendation itself includes a short description, prefer it
                if paired_text == "No context available":
                    for key in ("description", "context", "note"):
                        if rec.get(key):
                            paired_text = str(rec.get(key))
                            break

                # ensure paired_context is a short, clear string
                rec["paired_context"] = paired_text.strip() if isinstance(paired_text, str) else paired_text
            
            # Add summary
            result["summary"] = recommendation_agent.get_recommendation_summary(recommendations)
            print(f"Generated recommendations with paired context: {recommendations}")
        
        print(f"Returning result: {result}")
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "agent": "RecommendationAgent",
            "status": "error",
            "result": str(e)
        }), 500


@recommendation_bp.route("/summary", methods=["POST"])
@require_auth
def get_recommendation_summary():
    """
    Get a summary of recommendations
    
    Expected input:
    {
        "recommendations": [
            {
            "violation_id": "...",
            "recommendation": "Update privacy consent forms",
            "expected_outcome": "User consent is clearly documented",
            "timeline": "2 weeks",
            "priority": "high",
            "resources_needed": "Legal team",
            "paired_context": "Section 4.2: Consent forms are missing user signature..."
            }
        ]
    }
    """
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        recommendations = data.get("recommendations", [])
        
        if not recommendations:
            return jsonify({"error": "No recommendations provided"}), 400
        
        summary = recommendation_agent.get_recommendation_summary(recommendations)
        return jsonify({
            "agent": "RecommendationAgent",
            "status": "success",
            "summary": summary
        })
        
    except Exception as e:
        return jsonify({
            "agent": "RecommendationAgent",
            "status": "error",
            "result": str(e)
        }), 500
