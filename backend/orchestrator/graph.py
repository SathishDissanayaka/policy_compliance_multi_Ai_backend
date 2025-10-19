from typing import Dict, Any, List, TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from utils.prompts import MAIN_PROMPT
from agents.chuck_retriever import Retriever
from agents.chunk_retriever_temp import TempRetriever
from agents.attached_document_processor import DocumentProcessorTemp
from langchain_google_genai import ChatGoogleGenerativeAI
import os
import tempfile
import requests
from db.connection import get_db

# --- TypedDict for orchestrator state ---
class OrchestratorState(TypedDict, total=False):
    session_id: str
    user_id: str
    message: str
    document_url: str
    safe_session_id: str
    history: List[BaseMessage]
    policy_context: Any
    doc_context: Any
    tmp_file_path: str
    full_user_message: str
    llm_response: BaseMessage
    response: str

# --- Session management moved to orchestrator ---
def get_history_from_orchestrator(state: OrchestratorState) -> List[BaseMessage]:
    """Get history from orchestrator's session management."""
    orchestrator = state.get("orchestrator")
    if orchestrator:
        return orchestrator.get_session_history(state["session_id"], state.get("user_id"))
    else:
        # Fallback for backward compatibility
        from .orchestrator import get_orchestrator
        return get_orchestrator().get_session_history(state["session_id"], state.get("user_id"))

# --- Helper to serialize LangChain messages ---
def serialize_messages(messages: List[BaseMessage]) -> List[Dict[str, str]]:
    return [{"type": type(msg).__name__, "content": msg.content} for msg in messages]

# --- Orchestrator nodes ---
# Note: Intent classification is handled by the main orchestrator before routing to graphs
# Graph nodes focus on their specific functionality without caring about intent

def input_node(state: OrchestratorState) -> OrchestratorState:
    print(f"[INPUT_NODE] Starting with state keys: {list(state.keys())}")
    print(f"[INPUT_NODE] Session ID: {state.get('session_id')}")
    print(f"[INPUT_NODE] Message: {state.get('message')}")
    if state.get("document_url"):
        print(f"[INPUT_NODE] Document URL: {state.get('document_url')}")
    assert state.get("session_id"), "session_id required"
    assert state.get("message"), "message required"
    assert state.get("user_id"), "user_id required"
    safe_session_id = state["session_id"].replace("-", "_")
    print("[INPUT_NODE] Validation passed")
    return {"safe_session_id": safe_session_id}

def session_history_node(state: OrchestratorState) -> OrchestratorState:
    print(f"[SESSION_HISTORY_NODE] Getting history for session: {state['session_id']}")
    history = get_history_from_orchestrator(state)
    print(f"[SESSION_HISTORY_NODE] Retrieved {len(history)} messages from history")
    print(f"[SESSION_HISTORY_NODE] History types: {[type(msg).__name__ for msg in history]}")
    return {"history": history}

_policy_retriever = Retriever()
_temp_retriever = TempRetriever()
_doc_processor = DocumentProcessorTemp()

def policy_retriever_node(state: OrchestratorState) -> OrchestratorState:
    message = state["message"]
    print(f"[POLICY_RETRIEVER_NODE] Retrieving chunks for message: {message[:100]}...")
    policy_context = _policy_retriever.retrieve_chunks(message)
    print(f"[POLICY_RETRIEVER_NODE] Retrieved {len(policy_context) if policy_context else 0} chunks")
    print(f"[POLICY_RETRIEVER_NODE] Policy context type: {type(policy_context)}")
    return {"policy_context": policy_context}

def context_combination_node(state: OrchestratorState) -> OrchestratorState:
    message = state["message"]
    policy_context = state.get("policy_context") or []
    doc_context = state.get("doc_context") or []
    print(f"[CONTEXT_COMBINATION_NODE] Message: {message[:100]}...")
    print(f"[CONTEXT_COMBINATION_NODE] Policy context length: {len(policy_context) if policy_context else 0}")
    print(f"[CONTEXT_COMBINATION_NODE] Document context length: {len(doc_context) if doc_context else 0}")
    combined_context = f"""
    Policy Context: {str(policy_context)}
    Document Context: {str(doc_context)}
    """
    full_message = f"User Message: {message}\nContext: {combined_context}"
    print(f"[CONTEXT_COMBINATION_NODE] Full message length: {len(full_message)}")
    return {"full_user_message": full_message}

_LLM = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
    google_api_key=os.getenv("GEMINI_API_KEY"),
)

def llm_node(state: OrchestratorState) -> OrchestratorState:
    history = state["history"]
    print(f"[LLM_NODE] History has {len(history)} messages")
    print(f"[LLM_NODE] Full user message length: {len(state['full_user_message'])}")
    try:
        # Add system prompt at the beginning of conversation
        system_message = SystemMessage(content=MAIN_PROMPT)
        convo = [system_message] + history + [HumanMessage(content=state["full_user_message"])]
        print(f"[LLM_NODE] Total conversation length: {len(convo)} messages")
        print("[LLM_NODE] Invoking LLM...")
        response = _LLM.invoke(convo)
        print(f"[LLM_NODE] LLM response type: {type(response)}")
        print(f"[LLM_NODE] Response content length: {len(response.content) if response.content else 0}")
        return {"response": response.content}
    except Exception as e:
        print(f"[LLM_NODE] ERROR invoking LLM: {e}")
        import traceback
        traceback.print_exc()
        # Fallback response to keep pipeline moving and allow persistence
        fallback = "I'm temporarily unavailable to generate a detailed answer, but I've recorded your question."
        return {"response": fallback}

def session_update_node(state: OrchestratorState) -> OrchestratorState:
    session_id = state["session_id"]
    user_id = state.get("user_id")
    print(f"[SESSION_UPDATE_NODE] Updating session: {session_id}")

    # Use orchestrator's session management
    orchestrator = state.get("orchestrator")
    user_message = state.get("message", "")  # Only persist the original user query
    if orchestrator:
        orchestrator.update_session_history(
            session_id,
            user_id,
            user_message,
            state.get("response", "")
        )
        print(f"[SESSION_UPDATE_NODE] Updated session via orchestrator")
    else:
        # Fallback for backward compatibility
        from .orchestrator import get_orchestrator
        get_orchestrator().update_session_history(
            session_id,
            user_id,
            user_message,
            state.get("response", "")
        )
        print(f"[SESSION_UPDATE_NODE] Updated session via fallback orchestrator")

    return {}

def output_node(state: OrchestratorState) -> Dict[str, Any]:
    print("[OUTPUT_NODE] Starting output processing...")
    # Don't directly return BaseMessage objects; only return primitives
    response_text = state.get("response", "")
    print(f"[OUTPUT_NODE] Response text type: {type(response_text)}")
    print(f"[OUTPUT_NODE] Response text length: {len(response_text) if response_text else 0}")
    
    # If you want to include session history, serialize it
    session_id = state.get("session_id")
    history_serialized = []
    if session_id:
        print(f"[OUTPUT_NODE] Serializing history for session: {session_id}")
        history = get_history_from_orchestrator(state)
        print(f"[OUTPUT_NODE] History to serialize has {len(history)} messages")
        history_serialized = [{"type": type(msg).__name__, "content": msg.content} 
                              for msg in history]
        print(f"[OUTPUT_NODE] Serialized {len(history_serialized)} messages")
    
    result = {
        "content": response_text,
        "history": history_serialized
    }
    print(f"[OUTPUT_NODE] Final result keys: {list(result.keys())}")
    print(f"[OUTPUT_NODE] Result types: {[(k, type(v)) for k, v in result.items()]}")
    return result

def document_download_node(state: OrchestratorState) -> OrchestratorState:
    print("=" * 60)
    print("[DOCUMENT_DOWNLOAD_NODE] STARTING DOCUMENT DOWNLOAD")
    print("=" * 60)
    url = state.get("document_url")
    if not url:
        print("[DOCUMENT_DOWNLOAD_NODE] No document_url provided. Skipping download.")
        print("[DOCUMENT_DOWNLOAD_NODE] State keys:", list(state.keys()))
        return {}
    
    print(f"[DOCUMENT_DOWNLOAD_NODE] Document URL detected: {url}")
    print(f"[DOCUMENT_DOWNLOAD_NODE] Session ID: {state.get('session_id')}")
    print(f"[DOCUMENT_DOWNLOAD_NODE] Safe Session ID: {state.get('safe_session_id')}")
    print("[DOCUMENT_DOWNLOAD_NODE] Starting download...")
    
    try:
        res = requests.get(url)
        print(f"[DOCUMENT_DOWNLOAD_NODE] HTTP Status: {res.status_code}")
        content = res.content
        print(f"[DOCUMENT_DOWNLOAD_NODE] Downloaded {len(content)} bytes")
        
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp.write(content)
        tmp.flush()
        tmp.close()
        print(f"[DOCUMENT_DOWNLOAD_NODE] Saved temp file at: {tmp.name}")
        print("[DOCUMENT_DOWNLOAD_NODE] Download completed successfully")
        return {"tmp_file_path": tmp.name}
        
    except Exception as e:
        print(f"[DOCUMENT_DOWNLOAD_NODE] ERROR during download: {str(e)}")
        import traceback
        traceback.print_exc()
        return {}

def document_processing_node(state: OrchestratorState) -> OrchestratorState:
    print("=" * 60)
    print("[DOCUMENT_PROCESSING_NODE] STARTING DOCUMENT PROCESSING")
    print("=" * 60)
    tmp_file_path = state.get("tmp_file_path")
    safe_session_id = state.get("safe_session_id")
    
    print(f"[DOCUMENT_PROCESSING_NODE] State keys: {list(state.keys())}")
    print(f"[DOCUMENT_PROCESSING_NODE] Temp file path: {tmp_file_path}")
    print(f"[DOCUMENT_PROCESSING_NODE] Safe session ID: {safe_session_id}")
    
    if not tmp_file_path:
        print("[DOCUMENT_PROCESSING_NODE] No temp file path found. Skipping processing.")
        return {}
    
    if not safe_session_id:
        print("[DOCUMENT_PROCESSING_NODE] No safe session ID found. Cannot process.")
        return {}
    
    print(f"[DOCUMENT_PROCESSING_NODE] Processing temp file: {tmp_file_path}")
    print(f"[DOCUMENT_PROCESSING_NODE] For session: {safe_session_id}")
    print("[DOCUMENT_PROCESSING_NODE] Calling document processor...")
    
    try:
        result = _doc_processor.process(tmp_file_path, safe_session_id)
        print(f"[DOCUMENT_PROCESSING_NODE] Processor result: {result}")
        print(f"[DOCUMENT_PROCESSING_NODE] Processor result status: {result.get('status') if result else 'No result'}")
        
        # Clean up temp file
        try:
            os.remove(tmp_file_path)
            print(f"[DOCUMENT_PROCESSING_NODE] Successfully removed temp file: {tmp_file_path}")
        except Exception as e:
            print(f"[DOCUMENT_PROCESSING_NODE] Failed to remove temp file: {e}")
        
        print("[DOCUMENT_PROCESSING_NODE] Processing completed successfully")
        return {}
        
    except Exception as e:
        print(f"[DOCUMENT_PROCESSING_NODE] ERROR during processing: {str(e)}")
        import traceback
        traceback.print_exc()
        return {}

def document_retriever_node(state: OrchestratorState) -> OrchestratorState:
    print("=" * 60)
    print("[DOCUMENT_RETRIEVER_NODE] STARTING DOCUMENT RETRIEVAL")
    print("=" * 60)
    question = state["message"]
    safe_session_id = state.get("safe_session_id")
    document_url = state.get("document_url")
    
    print(f"[DOCUMENT_RETRIEVER_NODE] Question: {question[:100]}...")
    print(f"[DOCUMENT_RETRIEVER_NODE] Safe session ID: {safe_session_id}")
    print(f"[DOCUMENT_RETRIEVER_NODE] Document URL: {document_url}")
    print(f"[DOCUMENT_RETRIEVER_NODE] State keys: {list(state.keys())}")
    
    # Check if we have a document context to retrieve from
    if not safe_session_id:
        print("[DOCUMENT_RETRIEVER_NODE] No safe session ID. Skipping temp retrieval.")
        return {"doc_context": []}
    
    print(f"[DOCUMENT_RETRIEVER_NODE] Calling temp retriever for session: {safe_session_id}")
    print("[DOCUMENT_RETRIEVER_NODE] Attempting to retrieve chunks from temporary document store...")
    
    try:
        doc_results = _temp_retriever.retrieve_chunks(question, safe_session_id)
        print(f"[DOCUMENT_RETRIEVER_NODE] Temp retriever returned: {type(doc_results)}")
        print(f"[DOCUMENT_RETRIEVER_NODE] Temp retriever result: {doc_results}")
        
        if isinstance(doc_results, dict):
            status = doc_results.get("status")
            chunks = doc_results.get("chunks", [])
            print(f"[DOCUMENT_RETRIEVER_NODE] Retrieval status: {status}")
            print(f"[DOCUMENT_RETRIEVER_NODE] Number of chunks: {len(chunks)}")
            
            if status == "success":
                doc_context = chunks
            else:
                print(f"[DOCUMENT_RETRIEVER_NODE] Retrieval failed with status: {status}")
                doc_context = []
        else:
            print(f"[DOCUMENT_RETRIEVER_NODE] Unexpected result type: {type(doc_results)}")
            doc_context = []
        
        print(f"[DOCUMENT_RETRIEVER_NODE] Final doc_context length: {len(doc_context)}")
        return {"doc_context": doc_context}
        
    except Exception as e:
        print(f"[DOCUMENT_RETRIEVER_NODE] ERROR during retrieval: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"doc_context": []}

# --- Build the state graph ---
def build_company_policy_graph():
    graph = StateGraph(OrchestratorState)
    graph.add_node("input", input_node)
    graph.add_node("history", session_history_node)
    graph.add_node("doc_download", document_download_node)
    graph.add_node("doc_process", document_processing_node)
    graph.add_node("policy_retriever", policy_retriever_node)
    graph.add_node("doc_retriever", document_retriever_node)
    graph.add_node("context_combine", context_combination_node)
    graph.add_node("llm", llm_node)
    graph.add_node("session_update", session_update_node)
    graph.add_node("output", output_node)

    graph.add_edge(START, "input")
    graph.add_edge("input", "history")
    
    # Conditional: if document_url is provided, go through doc pipeline first; else go straight to policy
    def route_after_history(state: OrchestratorState):
        print("=" * 60)
        print("[ROUTER] ROUTING AFTER HISTORY NODE")
        print("=" * 60)
        safe_session_id = state.get("safe_session_id")
        document_url = state.get("document_url")
        
        print(f"[ROUTER] Safe session ID: {safe_session_id}")
        print(f"[ROUTER] Document URL: {document_url}")
        print(f"[ROUTER] State keys: {list(state.keys())}")
        
        has_temp = False
        try:
            if safe_session_id:
                print(f"[ROUTER] Checking for existing temp table: temp_documents_{safe_session_id}")
                conn = get_db()
                cur = conn.cursor()
                cur.execute("SELECT to_regclass(%s)", (f"public.temp_documents_{safe_session_id}",))
                exists_row = cur.fetchone()
                cur.close()
                conn.close()
                has_temp = bool(exists_row and exists_row[0])
                print(f"[ROUTER] Temp table exists: {has_temp}")
        except Exception as e:
            print(f"[ROUTER] Error checking temp table: {e}")
            has_temp = False

        if has_temp:
            print("[ROUTER] Decision: has_doc (existing temp table found)")
            return "has_doc"  # already processed doc for this session
        if document_url:
            print("[ROUTER] Decision: with_doc (new document URL provided)")
            return "with_doc"  # new doc provided, needs processing
        print("[ROUTER] Decision: no_doc (no document)")
        return "no_doc"

    graph.add_conditional_edges(
        "history",
        route_after_history,
        {
            "with_doc": "doc_download",
            "has_doc": "policy_retriever",
            "no_doc": "policy_retriever",
        },
    )

    graph.add_edge("doc_download", "doc_process")
    graph.add_edge("doc_process", "policy_retriever")

    # Conditional: after policy retrieval, if we have a document, also retrieve from temp; else skip to combine
    def route_after_policy(state: OrchestratorState):
        print("=" * 60)
        print("[ROUTER] ROUTING AFTER POLICY RETRIEVAL")
        print("=" * 60)
        safe_session_id = state.get("safe_session_id")
        document_url = state.get("document_url")
        
        print(f"[ROUTER] Safe session ID: {safe_session_id}")
        print(f"[ROUTER] Document URL: {document_url}")
        
        has_temp = False
        try:
            if safe_session_id:
                print(f"[ROUTER] Checking for temp table: temp_documents_{safe_session_id}")
                conn = get_db()
                cur = conn.cursor()
                cur.execute("SELECT to_regclass(%s)", (f"public.temp_documents_{safe_session_id}",))
                exists_row = cur.fetchone()
                cur.close()
                conn.close()
                has_temp = bool(exists_row and exists_row[0])
                print(f"[ROUTER] Temp table exists: {has_temp}")
        except Exception as e:
            print(f"[ROUTER] Error checking temp table after policy: {e}")
            has_temp = False

        if has_temp:
            print("[ROUTER] Decision: need_doc (temp table found, will retrieve document context)")
            return "need_doc"
        else:
            print("[ROUTER] Decision: no_doc_needed (no temp table, skip document retrieval)")
            return "no_doc_needed"

    graph.add_conditional_edges(
        "policy_retriever",
        route_after_policy,
        {
            "need_doc": "doc_retriever",
            "no_doc_needed": "context_combine",
        },
    )

    graph.add_edge("doc_retriever", "context_combine")
    graph.add_edge("context_combine", "llm")
    graph.add_edge("llm", "session_update")
    graph.add_edge("session_update", "output")
    graph.add_edge("output", END)

    return graph.compile()

# --- Run the graph safely ---
def run_company_policy(session_id: str, message: str, document_url: str = None) -> str:
    print(f"[RUN_COMPANY_POLICY] Starting company policy graph with session_id: {session_id}")
    print(f"[RUN_COMPANY_POLICY] Message: {message[:100]}...")
    if document_url:
        print(f"[RUN_COMPANY_POLICY] Document URL detected: {document_url}")
    
    try:
        app = build_company_policy_graph()
        initial_state: OrchestratorState = {
            "session_id": session_id,
            "message": message,
            "document_url": document_url,
        }
        print(f"[RUN_COMPANY_POLICY] Initial state: {list(initial_state.keys())}")
        
        print("[RUN_COMPANY_POLICY] Invoking graph...")
        final_state = app.invoke(initial_state)
        print(f"[RUN_COMPANY_POLICY] Final state keys: {list(final_state.keys())}")
        print(f"[RUN_COMPANY_POLICY] Final state types: {[(k, type(v)) for k, v in final_state.items()]}")
        
        # Extract just the content string like the old route
        # The output_node puts the response in "content" key, not "response"
        content = final_state.get("content", "") or final_state.get("response", "")
        print(f"[RUN_COMPANY_POLICY] Extracted content: {repr(content[:100]) if content else 'None'}")
        print(f"[RUN_COMPANY_POLICY] Returning content type: {type(content)}")
        print(f"[RUN_COMPANY_POLICY] Content length: {len(content) if content else 0}")
        
        return content
        
    except Exception as e:
        print(f"[RUN_COMPANY_POLICY] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"Error processing request: {str(e)}"