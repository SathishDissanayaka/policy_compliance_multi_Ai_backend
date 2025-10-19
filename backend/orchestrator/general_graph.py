from typing import Dict, Any, List, TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
import os

# --- TypedDict for general purpose state ---
class GeneralPurposeState(TypedDict, total=False):
    session_id: str
    user_id: str
    message: str
    safe_session_id: str
    history: List[BaseMessage]
    response: str

# --- General purpose nodes ---
# Note: Intent classification is handled by the main orchestrator before routing to graphs
# Graph nodes focus on their specific functionality without caring about intent

def general_input_node(state: GeneralPurposeState) -> GeneralPurposeState:
    print(f"[GENERAL_INPUT_NODE] Starting with state keys: {list(state.keys())}")
    print(f"[GENERAL_INPUT_NODE] Session ID: {state.get('session_id')}")
    print(f"[GENERAL_INPUT_NODE] Message: {state.get('message')}")
    assert state.get("session_id"), "session_id required"
    assert state.get("message"), "message required"
    assert state.get("user_id"), "user_id required"
    safe_session_id = state["session_id"].replace("-", "_")
    print("[GENERAL_INPUT_NODE] Validation passed")
    return {"safe_session_id": safe_session_id}

def general_history_node(state: GeneralPurposeState) -> GeneralPurposeState:
    print(f"[GENERAL_HISTORY_NODE] Getting history for session: {state['session_id']}")
    # Use orchestrator's session management
    orchestrator = state.get("orchestrator")
    if orchestrator:
        history = orchestrator.get_session_history(state["session_id"], state.get("user_id"))
    else:
        # Fallback
        from .orchestrator import get_orchestrator
        history = get_orchestrator().get_session_history(state["session_id"], state.get("user_id"))
    
    print(f"[GENERAL_HISTORY_NODE] Retrieved {len(history)} messages from history")
    print(f"[GENERAL_HISTORY_NODE] History types: {[type(msg).__name__ for msg in history]}")
    return {"history": history}

# Initialize LLM for general purpose
_LLM = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.7,  # Higher temperature for more creative responses
    google_api_key=os.getenv("GEMINI_API_KEY"),
)

def general_llm_node(state: GeneralPurposeState) -> GeneralPurposeState:
    message = state["message"]
    history = state["history"]
    print(f"[GENERAL_LLM_NODE] History has {len(history)} messages")
    print(f"[GENERAL_LLM_NODE] User message: {message[:100]}...")
    try:
        # Create conversation with focused system message
        system_message = SystemMessage(content="""You are a helpful assistant for a policy compliance system. Your role is strictly limited to:

1. CASUAL CONVERSATION: Greetings, small talk, pleasantries (hello, how are you, good morning, etc.)
2. SYSTEM CAPABILITIES: Explaining what the system can help with regarding company policies
3. CONVERSATION HISTORY: Answering questions about previous messages in the conversation

IMPORTANT BOUNDARIES:
- DO NOT answer questions about topics outside of company policies (food, weather, general knowledge, personal advice, etc.)
- DO NOT provide information on topics you're not trained for
- DO NOT assist with unethical or illegal requests (bypassing policies, violating regulations, fraudulent activities)
- If asked about non-policy topics, politely but firmly explain that you can only help with company policy questions
- If asked about unethical or illegal activities, firmly refuse to assist and direct to appropriate authorities
- Be friendly but maintain clear boundaries about your scope

CONVERSATION HISTORY:
- You CAN answer questions about what was discussed in previous messages
- You CAN recall and summarize previous questions and topics
- You CAN help users understand what they've asked before

RESPONSES FOR OUT-OF-SCOPE QUESTIONS:
"I'm designed to help with company policy questions and casual conversation. I can't provide information about [topic]. I can help you with questions about our company policies, HR procedures, employee handbook, or just have a friendly chat!"

RESPONSES FOR UNETHICAL QUESTIONS:
"I cannot assist with requests that involve unethical or illegal activities. Please consult with appropriate authorities or legal counsel for such matters."

Be warm and helpful within your defined scope, but firm about boundaries and ethical standards.""")
    
        convo = [system_message] + history + [HumanMessage(content=message)]
        print(f"[GENERAL_LLM_NODE] Total conversation length: {len(convo)} messages")
        print("[GENERAL_LLM_NODE] Invoking LLM...")
        response = _LLM.invoke(convo)
        print(f"[GENERAL_LLM_NODE] LLM response type: {type(response)}")
        print(f"[GENERAL_LLM_NODE] Response content length: {len(response.content) if response.content else 0}")
        return {"response": response.content}
    except Exception as e:
        print(f"[GENERAL_LLM_NODE] ERROR invoking LLM: {e}")
        import traceback
        traceback.print_exc()
        fallback = "I'm here to help with policy questions, but I can't generate a response right now."
        return {"response": fallback}

def general_session_update_node(state: GeneralPurposeState) -> GeneralPurposeState:
    session_id = state["session_id"]
    print(f"[GENERAL_SESSION_UPDATE_NODE] Updating session: {session_id}")
    
    # Use orchestrator's session management
    orchestrator = state.get("orchestrator")
    if orchestrator:
        orchestrator.update_session_history(
            session_id,
            state.get("user_id"),
            state["message"],
            state.get("response", "")
        )
        print(f"[GENERAL_SESSION_UPDATE_NODE] Updated session via orchestrator")
    else:
        # Fallback
        from .orchestrator import get_orchestrator
        get_orchestrator().update_session_history(
            session_id,
            state.get("user_id"),
            state["message"],
            state.get("response", "")
        )
        print(f"[GENERAL_SESSION_UPDATE_NODE] Updated session via fallback orchestrator")
    
    return {}

def general_output_node(state: GeneralPurposeState) -> Dict[str, Any]:
    print("[GENERAL_OUTPUT_NODE] Starting output processing...")
    response_text = state.get("response", "")
    print(f"[GENERAL_OUTPUT_NODE] Response text type: {type(response_text)}")
    print(f"[GENERAL_OUTPUT_NODE] Response text length: {len(response_text) if response_text else 0}")
    
    # Serialize history for response
    session_id = state.get("session_id")
    history_serialized = []
    if session_id:
        print(f"[GENERAL_OUTPUT_NODE] Serializing history for session: {session_id}")
        orchestrator = state.get("orchestrator")
        if orchestrator:
            history = orchestrator.get_session_history(session_id, state.get("user_id"))
        else:
            from .orchestrator import get_orchestrator
            history = get_orchestrator().get_session_history(session_id, state.get("user_id"))
        
        print(f"[GENERAL_OUTPUT_NODE] History to serialize has {len(history)} messages")
        history_serialized = [{"type": type(msg).__name__, "content": msg.content} 
                              for msg in history]
        print(f"[GENERAL_OUTPUT_NODE] Serialized {len(history_serialized)} messages")
    
    result = {
        "content": response_text,
        "history": history_serialized
    }
    print(f"[GENERAL_OUTPUT_NODE] Final result keys: {list(result.keys())}")
    print(f"[GENERAL_OUTPUT_NODE] Result types: {[(k, type(v)) for k, v in result.items()]}")
    return result

# --- Build the general purpose graph ---
def build_general_purpose_graph():
    print("[GENERAL_GRAPH] Building general purpose graph")
    graph = StateGraph(GeneralPurposeState)
    
    # Add nodes
    graph.add_node("input", general_input_node)
    graph.add_node("history", general_history_node)
    graph.add_node("llm", general_llm_node)
    graph.add_node("session_update", general_session_update_node)
    graph.add_node("output", general_output_node)
    
    # Add edges - simple linear flow for general purpose
    graph.add_edge(START, "input")
    graph.add_edge("input", "history")
    graph.add_edge("history", "llm")
    graph.add_edge("llm", "session_update")
    graph.add_edge("session_update", "output")
    graph.add_edge("output", END)
    
    print("[GENERAL_GRAPH] General purpose graph built successfully")
    return graph.compile()

# --- Run the general purpose graph ---
def run_general_purpose(session_id: str, message: str) -> str:
    print(f"[RUN_GENERAL_PURPOSE] Starting general purpose graph with session_id: {session_id}")
    print(f"[RUN_GENERAL_PURPOSE] Message: {message[:100]}...")
    
    try:
        app = build_general_purpose_graph()
        initial_state: GeneralPurposeState = {
            "session_id": session_id,
            "message": message,
        }
        print(f"[RUN_GENERAL_PURPOSE] Initial state: {list(initial_state.keys())}")
        
        print("[RUN_GENERAL_PURPOSE] Invoking graph...")
        final_state = app.invoke(initial_state)
        print(f"[RUN_GENERAL_PURPOSE] Final state keys: {list(final_state.keys())}")
        
        content = final_state.get("content", "") or final_state.get("response", "")
        print(f"[RUN_GENERAL_PURPOSE] Extracted content: {repr(content[:100]) if content else 'None'}")
        print(f"[RUN_GENERAL_PURPOSE] Content length: {len(content) if content else 0}")
        
        return content
        
    except Exception as e:
        print(f"[RUN_GENERAL_PURPOSE] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"Error processing request: {str(e)}"
