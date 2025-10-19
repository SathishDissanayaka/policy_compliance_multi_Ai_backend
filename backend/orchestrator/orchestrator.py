
from typing import Dict, Any, List, Optional
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
import os
from .graph import build_company_policy_graph
from .general_graph import build_general_purpose_graph
from .executor import create_stream_generator
from .event_formatter import format_event_for_ui, serialize_payload_for_sse
import asyncio
import queue as _queue
import threading
import json
from db.repositories.chat_repository import ChatRepository

# --- Intent classification prompts ---
INTENT_CLASSIFICATION_PROMPT = """
You are an intent classifier for a policy compliance system. Analyze the user's message and classify it into one of these categories:

1. "company_policy" - Questions about company policies, HR policies, employee handbook, compliance, procedures, etc.
2. "general" - ONLY casual conversation (greetings, small talk) or questions about what the system can do

Respond with ONLY the category name (either "company_policy" or "general").

Examples:
- "What is our vacation policy?" -> company_policy
- "How do I submit a leave request?" -> company_policy
- "What are the dress code requirements?" -> company_policy
- "Hello, how are you?" -> general
- "Hi there!" -> general
- "What can you help me with?" -> general
- "Good morning!" -> general
- "What were the questions I asked previously?" -> general
- "What did I ask before?" -> general
- "Can you recall our conversation history?" -> general
- "What should I eat?" -> general (will be handled by general agent with scope boundaries)
- "What's the weather like?" -> general (will be handled by general agent with scope boundaries)
- "Tell me a joke" -> general (will be handled by general agent with scope boundaries)

When in doubt, classify as "general" to ensure unrelated questions don't get answered.
"""

class Orchestrator:
    """
    Central orchestrator that classifies user intents and routes to appropriate pipelines.
    Manages persistent session context and coordinates between different graph pipelines.
    """
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
            google_api_key=os.getenv("GEMINI_API_KEY"),
        )
        self.company_policy_graph = None
        self.general_purpose_graph = None
        self.chat_repo = ChatRepository()
        print("[ORCHESTRATOR] Initialized orchestrator")

    def get_session_history(self, session_id: str, user_id: str) -> List[BaseMessage]:
        """Load session history from the database."""
        try:
            db_messages = self.chat_repo.get_messages(session_id)
            history = []
            for msg in db_messages:
                if msg['role'] == 'user':
                    history.append(HumanMessage(content=msg['content']))
                elif msg['role'] == 'assistant':
                    history.append(AIMessage(content=msg['content']))
            if not history:
                history = [SystemMessage(content="You are a helpful assistant.")]
            return history
        except Exception as e:
            print(f"[ORCHESTRATOR] Failed to load history: {e}")
            return [SystemMessage(content="You are a helpful assistant.")]

    def update_session_history(self, session_id: str, user_id: str, human_message: str, ai_response: str):
        """Save conversation to the database."""
        try:
            # Ensure session exists
            self.chat_repo.get_or_create_session(
                session_id=session_id,
                user_id=user_id,
                title=human_message[:50] if human_message else "New Chat"
            )
            # Save user message
            self.chat_repo.save_message(
                session_id=session_id,
                role='user',
                content=human_message,
                metadata=None
            )
            # Save assistant response
            self.chat_repo.save_message(
                session_id=session_id,
                role='assistant',
                content=ai_response,
                metadata=None
            )
            print(f"[ORCHESTRATOR] Saved conversation to database - Session: {session_id}")
        except Exception as e:
            print(f"[ORCHESTRATOR] Failed to save history: {e}")
    
    def classify_intent(self, message: str, session_id: str) -> str:
        """Classify user intent using rule-based approach first, then LLM if needed."""
        print(f"[ORCHESTRATOR] Classifying intent for message: {message[:100]}...")
        
        # First try rule-based classification
        intent = self._rule_based_classification(message)
        if intent:
            print(f"[ORCHESTRATOR] Rule-based classification: {intent}")
            return intent
        
        # If rule-based fails, use LLM
        print(f"[ORCHESTRATOR] Rule-based classification uncertain, using LLM...")
        return self._llm_classification(message, session_id)
    
    def _rule_based_classification(self, message: str) -> str:
        """Rule-based intent classification using keywords."""
        message_lower = message.lower().strip()
        
        # Company policy keywords
        policy_keywords = [
            'policy', 'policies', 'hr', 'human resources', 'vacation', 'leave', 'sick', 'holiday',
            'dress code', 'attendance', 'remote work', 'work from home', 'benefits', 'insurance',
            'harassment', 'discrimination', 'complaint', 'procedure', 'handbook', 'employee',
            'employment', 'contract', 'agreement', 'disciplinary', 'termination', 'salary',
            'pay', 'compensation', 'bonus', 'raise', 'promotion', 'performance', 'training',
            'development', 'onboarding', 'orientation', 'safety', 'security', 'compliance',
            'regulation', 'legal', 'law', 'rights', 'responsibilities', 'workplace', 'office',
            'company', 'organization', 'corporate', 'business', 'work', 'job', 'career'
        ]
        
        # Casual conversation keywords
        casual_keywords = [
            'hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening',
            'how are you', 'what\'s up', 'thanks', 'thank you', 'bye', 'goodbye',
            'see you', 'have a good', 'nice to meet', 'pleasure', 'welcome'
        ]
        
        # System capability keywords
        capability_keywords = [
            'what can you', 'what do you', 'how can you', 'what are you', 'help me',
            'assist', 'support', 'capabilities', 'features', 'functions', 'do for'
        ]
        
        # Conversation history keywords
        history_keywords = [
            'previous', 'before', 'earlier', 'last time', 'conversation', 'chat',
            'history', 'asked', 'questions', 'messages', 'what did i', 'what was',
            'recall', 'remember', 'past', 'earlier', 'ago'
        ]
        
        # Check for policy keywords
        policy_matches = sum(1 for keyword in policy_keywords if keyword in message_lower)
        if policy_matches > 0:
            print(f"[ORCHESTRATOR] Found {policy_matches} policy keywords")
            return "company_policy"
        
        # Check for casual conversation
        casual_matches = sum(1 for keyword in casual_keywords if keyword in message_lower)
        if casual_matches > 0:
            print(f"[ORCHESTRATOR] Found {casual_matches} casual keywords")
            return "general"
        
        # Check for system capability questions
        capability_matches = sum(1 for keyword in capability_keywords if keyword in message_lower)
        if capability_matches > 0:
            print(f"[ORCHESTRATOR] Found {capability_matches} capability keywords")
            return "general"
        
        # Check for conversation history questions
        history_matches = sum(1 for keyword in history_keywords if keyword in message_lower)
        if history_matches > 0:
            print(f"[ORCHESTRATOR] Found {history_matches} history keywords")
            return "general"
        
        # If no clear matches, return None to trigger LLM classification
        print(f"[ORCHESTRATOR] No clear rule-based classification found")
        return None
    
    def _llm_classification(self, message: str, session_id: str, user_id: Optional[str] = None) -> str:
        """LLM-based intent classification as fallback."""
        print(f"[ORCHESTRATOR] Using LLM for intent classification...")
        
        try:
            # Get session history for context
            history = self.get_session_history(session_id, user_id)
            
            # Create classification prompt
            classification_messages = [
                SystemMessage(content=INTENT_CLASSIFICATION_PROMPT),
                HumanMessage(content=message)
            ]
            
            # Get classification from LLM
            response = self.llm.invoke(classification_messages)
            intent = response.content.strip().lower()
            
            # Validate intent
            if intent not in ["company_policy", "general"]:
                print(f"[ORCHESTRATOR] Invalid LLM intent '{intent}', defaulting to 'general'")
                intent = "general"
            
            print(f"[ORCHESTRATOR] LLM classified intent: {intent}")
            return intent
            
        except Exception as e:
            print(f"[ORCHESTRATOR] Error in LLM classification: {e}")
            return "general"  # Default fallback
    
    def get_graph(self, intent: str):
        """Get the appropriate graph for the intent."""
        print(f"[ORCHESTRATOR] Getting graph for intent: {intent}")
        
        if intent == "company_policy":
            print(f"[ORCHESTRATOR] Routing to COMPANY POLICY pipeline")
            if self.company_policy_graph is None:
                print(f"[ORCHESTRATOR] Building company policy graph...")
                self.company_policy_graph = build_company_policy_graph()
                print("[ORCHESTRATOR] Company policy graph built successfully")
            else:
                print(f"[ORCHESTRATOR] Using existing company policy graph")
            return self.company_policy_graph
        elif intent == "general":
            print(f"[ORCHESTRATOR] Routing to GENERAL PURPOSE pipeline")
            if self.general_purpose_graph is None:
                print(f"[ORCHESTRATOR] Building general purpose graph...")
                self.general_purpose_graph = build_general_purpose_graph()
                print("[ORCHESTRATOR] General purpose graph built successfully")
            else:
                print(f"[ORCHESTRATOR] Using existing general purpose graph")
            return self.general_purpose_graph
        else:
            print(f"[ORCHESTRATOR] ERROR: Unknown intent '{intent}'")
            raise ValueError(f"Unknown intent: {intent}")
    
    def create_stream_generator(self, session_id: str, message: str, document_url: Optional[str] = None, user_id: Optional[str] = None):
        """Create a stream generator that routes through the orchestrator."""
        print("=" * 80)
        print(f"[ORCHESTRATOR] Creating stream generator for session: {session_id}")
        print(f"[ORCHESTRATOR] Message: {message[:100]}...")
        if document_url:
            print(f"[ORCHESTRATOR] Document URL: {document_url}")
        print("=" * 80)
        
        # Classify intent
        print(f"[ORCHESTRATOR] Step 1: Classifying intent...")
        intent = self.classify_intent(message, session_id)
        print(f"[ORCHESTRATOR] Intent classification result: {intent}")
        
        # Get appropriate graph
        print(f"[ORCHESTRATOR] Step 2: Getting appropriate graph...")
        graph = self.get_graph(intent)
        print(f"[ORCHESTRATOR] Graph obtained: {type(graph).__name__}")
        
        # Create initial state with orchestrator context
        print(f"[ORCHESTRATOR] Step 3: Creating initial state...")
        initial_state = {
            "session_id": session_id,
            "message": message,
            "document_url": document_url,
            "intent": intent,
            "orchestrator": self,  # Pass orchestrator reference for context access
            "user_id": user_id,
        }
        
        print(f"[ORCHESTRATOR] Initial state created with keys: {list(initial_state.keys())}")
        print(f"[ORCHESTRATOR] Intent being passed to graph: {intent}")
        print(f"[ORCHESTRATOR] Final routing decision: {intent.upper()} pipeline")
        print("=" * 80)
        
        # Create stream generator using the executor
        print(f"[ORCHESTRATOR] Step 4: Creating stream generator...")
        stream_gen = create_stream_generator(graph, initial_state)
        print(f"[ORCHESTRATOR] Stream generator created successfully")
        
        return stream_gen
    
    def get_global_context(self, session_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Get global context for a session."""
        # This can be extended to include more context like user preferences, 
        # previous intents, document references, etc.
        history = self.get_session_history(session_id, user_id)
        return {
            "session_id": session_id,
            "message_count": len(history),
            "last_intent": getattr(self, f"_last_intent_{session_id}", None),
            "context_data": getattr(self, f"_context_data_{session_id}", {}),
        }
    
    def update_global_context(self, session_id: str, **context_updates):
        """Update global context for a session."""
        setattr(self, f"_last_intent_{session_id}", context_updates.get("intent"))
        if "context_data" in context_updates:
            setattr(self, f"_context_data_{session_id}", context_updates["context_data"])
        print(f"[ORCHESTRATOR] Updated global context for session: {session_id}")


# Global orchestrator instance
_orchestrator = None

def get_orchestrator() -> Orchestrator:
    """Get the global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        print("[ORCHESTRATOR] Creating new global orchestrator instance...")
        _orchestrator = Orchestrator()
        print("[ORCHESTRATOR] Global orchestrator instance created successfully")
    else:
        print("[ORCHESTRATOR] Using existing global orchestrator instance")
    return _orchestrator
