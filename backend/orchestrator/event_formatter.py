import os
import json
from typing import Dict, Any, List, Optional


def _truncate(text, limit=140):
    """Truncate text to a specified limit."""
    if text is None:
        return ""
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _safe_session(value: str) -> str:
    """Convert session ID to safe format."""
    return (value or "").replace("-", "_")


def _extract_text(blob):
    """Extract text content from various data structures."""
    if blob is None:
        return ""
    if isinstance(blob, str):
        return blob
    if isinstance(blob, dict):
        for key in ("content", "text", "response"):
            if key in blob:
                return _extract_text(blob[key])
        parts = []
        for val in blob.values():
            chunk = _extract_text(val)
            if chunk:
                parts.append(chunk)
        return "".join(parts)
    if isinstance(blob, (list, tuple)):
        return "".join(_extract_text(part) for part in blob)
    if hasattr(blob, "content"):
        return _extract_text(getattr(blob, "content"))
    return str(blob)


def _extract_count(value):
    """Extract count from various data structures."""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value)
    return None


def _build_stage_payload(node: str, message: str, **extra):
    """Build a stage payload for UI events."""
    payload = {"type": "stage", "node": node, "message": message}
    if extra:
        payload.update({k: v for k, v in extra.items() if v is not None})
    return payload


def _extract_token(data_section):
    """Extract token from LLM streaming data."""
    if not isinstance(data_section, dict):
        return ""
    chunk = data_section.get("chunk") or data_section.get("delta")
    if chunk is None:
        return ""
    if isinstance(chunk, str):
        return chunk
    if isinstance(chunk, dict):
        content = chunk.get("content")
        if isinstance(content, list):
            return "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        if isinstance(content, str):
            return content
        if "text" in chunk:
            return str(chunk["text"])
    if hasattr(chunk, "content"):
        return _extract_text(chunk.content)
    if hasattr(chunk, "text"):
        return str(chunk.text)
    return _extract_text(chunk)


def _maybe_get_state(data_section: dict):
    """Extract state from data section."""
    if not isinstance(data_section, dict):
        return {}
    for key in ("state", "new_state", "updated_state"):
        state = data_section.get(key)
        if isinstance(state, dict):
            return state
    return {}


def format_event_for_ui(event: Dict[str, Any], initial_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Convert a raw LangGraph event into UI-friendly payloads.
    
    Args:
        event: Raw event dict from LangGraph
        initial_state: Initial state used for the graph execution
        
    Returns:
        List of UI payloads to send to the client
    """
    payloads = []
    
    try:
        node_name = (event.get("name") or "").lower()
        ev_type = event.get("event")
        data_section = event.get("data") or {}
        state_snapshot = _maybe_get_state(data_section)
        output_section = data_section.get("output") if isinstance(data_section, dict) else None
        
        print(f"[EVENT_FORMATTER] Processing event: {ev_type} from {node_name}")
        print(f"[EVENT_FORMATTER] Event keys: {list(event.keys())}")
        print(f"[EVENT_FORMATTER] Data section keys: {list(data_section.keys()) if isinstance(data_section, dict) else 'not dict'}")
        
        # Note: Intent classification is handled by the main orchestrator before routing
        # Graph nodes don't do intent classification, they just execute their specific logic

        if ev_type == "on_chat_model_stream":
            print(f"[EVENT_FORMATTER] Processing LLM stream event from {node_name}")
            token = _extract_token(data_section)
            if token:
                payloads.append({"type": "llm_stream", "node": node_name, "content": token})
                print(f"[EVENT_FORMATTER] Generated LLM stream payload with token: {token[:50]}...")

        elif ev_type == "on_chat_model_end":
            print(f"[EVENT_FORMATTER] Processing LLM end event from {node_name}")
            final_text = _extract_text(output_section or data_section)
            if final_text:
                payloads.append({"type": "llm_final", "node": node_name, "content": final_text})
                print(f"[EVENT_FORMATTER] Generated LLM final payload with text: {final_text[:100]}...")

        elif node_name in ("input", "input_node"):
            print(f"[EVENT_FORMATTER] Processing input node event: {ev_type}")
            if ev_type == "on_chain_start":
                payloads.append(
                    _build_stage_payload(
                        "input",
                        "Validating session & user input…",
                        session=_safe_session(initial_state.get("session_id")),
                        user_message=_truncate(initial_state.get("message"), 120),
                    )
                )
                print(f"[EVENT_FORMATTER] Generated input start payload")
            elif ev_type == "on_chain_end":
                safe_id = None
                if isinstance(output_section, dict):
                    safe_id = output_section.get("safe_session_id")
                if not safe_id:
                    safe_id = _safe_session(initial_state.get("session_id"))
                payloads.append(
                    _build_stage_payload(
                        "input",
                        "Session validated",
                        session=safe_id,
                    )
                )
                print(f"[EVENT_FORMATTER] Generated input end payload with safe_id: {safe_id}")

        elif node_name in ("history", "session_history_node") and ev_type == "on_chain_end":
            print(f"[EVENT_FORMATTER] Processing history node end event")
            history = None
            if isinstance(output_section, dict):
                history = output_section.get("history")
            if history is None and state_snapshot:
                history = state_snapshot.get("history")
            count = _extract_count(history) or 0
            payloads.append(
                _build_stage_payload(
                    "history",
                    f"Fetched {count} messages from history",
                    count=count,
                )
            )
            print(f"[EVENT_FORMATTER] Generated history payload with {count} messages")

        elif node_name in ("doc_download", "document_download_node"):
            if ev_type == "on_chain_start":
                url = initial_state.get("document_url") or state_snapshot.get("document_url")
                if url:
                    payloads.append(
                        _build_stage_payload(
                            "doc_download",
                            f"Downloading document from URL {_truncate(url, 100)}",
                        )
                    )
            elif ev_type == "on_chain_end":
                tmp_path = None
                if isinstance(output_section, dict):
                    tmp_path = output_section.get("tmp_file_path")
                if not tmp_path and state_snapshot:
                    tmp_path = state_snapshot.get("tmp_file_path")
                size_bytes = None
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        size_bytes = os.path.getsize(tmp_path)
                    except OSError:
                        size_bytes = None
                payloads.append(
                    _build_stage_payload(
                        "doc_download",
                        "Document downloaded",
                        bytes=size_bytes,
                        temp_path=_truncate(tmp_path, 80) if tmp_path else None,
                    )
                )

        elif node_name in ("doc_process", "document_processing_node"):
            if ev_type == "on_chain_start":
                payloads.append(
                    _build_stage_payload(
                        "doc_process",
                        "Processing downloaded document…",
                    )
                )
            elif ev_type == "on_chain_end":
                payloads.append(
                    _build_stage_payload(
                        "doc_process",
                        "Document chunks prepared for retrieval",
                    )
                )

        elif node_name in ("policy_retriever", "policy_retriever_node") and ev_type == "on_chain_end":
            print(f"[EVENT_FORMATTER] Processing policy retriever end event")
            policy_chunks = None
            if isinstance(output_section, dict):
                policy_chunks = output_section.get("policy_context")
            if policy_chunks is None and state_snapshot:
                policy_chunks = state_snapshot.get("policy_context")
            count = _extract_count(policy_chunks) or 0
            payloads.append(
                _build_stage_payload(
                    "policy_retriever",
                    f"Retrieved {count} policy chunks",
                    count=count,
                    sample=_truncate(policy_chunks[0] if count else "", 160)
                    if isinstance(policy_chunks, list)
                    else None,
                )
            )
            print(f"[EVENT_FORMATTER] Generated policy retriever payload with {count} chunks")

        elif node_name in ("doc_retriever", "document_retriever_node") and ev_type == "on_chain_end":
            doc_chunks = None
            if isinstance(output_section, dict):
                doc_chunks = output_section.get("doc_context")
            if doc_chunks is None and state_snapshot:
                doc_chunks = state_snapshot.get("doc_context")
            count = _extract_count(doc_chunks) or 0
            payloads.append(
                _build_stage_payload(
                    "doc_retriever",
                    f"Retrieved {count} document chunks",
                    count=count,
                    sample=_truncate(doc_chunks[0] if count else "", 160)
                    if isinstance(doc_chunks, list)
                    else None,
                )
            )

        elif node_name in ("context_combine", "context_combination_node") and ev_type == "on_chain_end":
            full_message = None
            if isinstance(output_section, dict):
                full_message = output_section.get("full_user_message")
            if not full_message and state_snapshot:
                full_message = state_snapshot.get("full_user_message")
            payloads.append(
                _build_stage_payload(
                    "context_combine",
                    "Combining policy and document context",
                    preview=_truncate(full_message, 200) if full_message else None,
                )
            )

        elif node_name in ("llm", "llm_node") and ev_type == "on_chain_start":
            payloads.append(
                _build_stage_payload(
                    "llm",
                    "Generating response with LLM…",
                )
            )

        elif node_name in ("session_update", "session_update_node") and ev_type == "on_chain_end":
            payloads.append(
                _build_stage_payload(
                    "session_update",
                    "Appending messages to session history",
                )
            )

        elif node_name in ("output", "output_node") and ev_type == "on_chain_end":
            print(f"[EVENT_FORMATTER] Processing output node end event")
            final_text = ""
            if isinstance(output_section, dict):
                final_text = _extract_text(output_section.get("content") or output_section)
                if not final_text:
                    final_text = output_section.get("response", "")
            if not final_text:
                final_text = _extract_text(data_section)
            payloads.append({"type": "final", "node": node_name, "content": final_text})
            print(f"[EVENT_FORMATTER] Generated final output payload with text: {final_text[:100]}...")

        elif ev_type in ("on_chain_start", "on_chain_end") and node_name:
            # Fallback generic progress event
            print(f"[EVENT_FORMATTER] Processing generic {ev_type} event for {node_name}")
            verb = "Starting" if ev_type == "on_chain_start" else "Finished"
            payloads.append(
                _build_stage_payload(
                    node_name,
                    f"{verb} node '{node_name}'",
                )
            )
            print(f"[EVENT_FORMATTER] Generated generic payload for {node_name}")

    except Exception as e:
        print(f"[EVENT_FORMATTER] ERROR processing event: {str(e)}")
        import traceback
        traceback.print_exc()
        payloads = [{"type": "error", "error": str(e)}]

    print(f"[EVENT_FORMATTER] Returning {len(payloads)} payloads for event: {ev_type} from {node_name}")
    return payloads


def serialize_payload_for_sse(payload: Dict[str, Any]) -> str:
    """Serialize a payload for Server-Sent Events."""
    try:
        sse_line = f"data: {json.dumps(payload)}\n\n"
        print(f"[SERIALIZER] Serialized payload: {payload.get('type', 'unknown')} - {len(sse_line)} chars")
        return sse_line
    except Exception as e:
        print(f"[SERIALIZER] Error serializing payload: {e}")
        raw = str(payload)[:200].replace("\n", "\\n")
        safe_payload = {"type": "event", "raw": raw}
        return f"data: {json.dumps(safe_payload)}\n\n"
