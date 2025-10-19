import asyncio
import json
import queue as _queue
import threading
from typing import Dict, Any, Generator, AsyncGenerator
from .event_formatter import format_event_for_ui, serialize_payload_for_sse


async def run_graph_stream(graph, initial_state: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Execute a LangGraph graph and yield raw event dicts.
    
    Args:
        graph: LangGraph graph instance
        initial_state: Initial state dict for the graph
        
    Yields:
        Raw event dicts from graph.astream_events
    """
    print(f"[EXECUTOR] Starting graph stream with initial state keys: {list(initial_state.keys())}")
    print(f"[EXECUTOR] Session ID: {initial_state.get('session_id')}")
    print(f"[EXECUTOR] Message: {initial_state.get('message', '')[:100]}...")
    if initial_state.get('document_url'):
        print(f"[EXECUTOR] Document URL: {initial_state.get('document_url')}")
    
    event_count = 0
    async for ev in graph.astream_events(initial_state, version="v2"):
        event_count += 1
        print(f"[EXECUTOR] Event #{event_count}: {ev.get('event', 'unknown')} from {ev.get('name', 'unknown')}")
        yield ev
    
    print(f"[EXECUTOR] Graph stream completed. Total events: {event_count}")


async def async_producer(graph, initial_state: Dict[str, Any], queue: _queue.Queue) -> None:
    """
    Run the compiled graph's async event stream and push serialized
    SSE payloads into the queue as they arrive.
    
    Args:
        graph: LangGraph graph instance
        initial_state: Initial state dict for the graph
        queue: Queue to push SSE payloads into
    """
    print(f"[ASYNC_PRODUCER] Starting async producer")
    print(f"[ASYNC_PRODUCER] Initial state: {list(initial_state.keys())}")
    
    try:
        # astream_events is an async generator of event dicts
        events = graph.astream_events(initial_state, version="v2")
        print(f"[ASYNC_PRODUCER] Created event stream")

        event_count = 0
        payload_count = 0
        async for event in events:
            event_count += 1
            print(f"[ASYNC_PRODUCER] Processing event #{event_count}: {event.get('event', 'unknown')} from {event.get('name', 'unknown')}")
            
            payloads = format_event_for_ui(event, initial_state)
            print(f"[ASYNC_PRODUCER] Generated {len(payloads)} UI payloads for event #{event_count}")
            
            for payload in payloads:
                try:
                    sse_line = serialize_payload_for_sse(payload)
                    queue.put(sse_line)
                    payload_count += 1
                    print(f"[ASYNC_PRODUCER] Queued payload #{payload_count}: {payload.get('type', 'unknown')}")
                except Exception as e:
                    print(f"[ASYNC_PRODUCER] Error serializing payload: {e}")
                    # Fallback for any serialization issues
                    raw = str(payload)[:200].replace("\n", "\\n")
                    safe_payload = {"type": "event", "raw": raw}
                    queue.put(f"data: {json.dumps(safe_payload)}\n\n")
                    payload_count += 1

        print(f"[ASYNC_PRODUCER] Completed processing. Total events: {event_count}, Total payloads: {payload_count}")

    except Exception as e:
        print(f"[ASYNC_PRODUCER] ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        queue.put(f"data: {json.dumps({'type':'error','error': str(e)})}\n\n")
    finally:
        print(f"[ASYNC_PRODUCER] Sending end signal and closing queue")
        try:
            queue.put(f"data: {json.dumps({'type':'end'})}\n\n")
        except Exception:
            queue.put("data: {\"type\": \"end\"}\n\n")
        queue.put(None)


def start_background_loop(graph, initial_state: Dict[str, Any], queue: _queue.Queue) -> None:
    """
    Thread target that runs the async producer.
    
    Args:
        graph: LangGraph graph instance
        initial_state: Initial state dict for the graph
        queue: Queue to push SSE payloads into
    """
    print(f"[BACKGROUND_LOOP] Starting background thread for async producer")
    print(f"[BACKGROUND_LOOP] Session ID: {initial_state.get('session_id')}")
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        print(f"[BACKGROUND_LOOP] Created new event loop")
        
        loop.run_until_complete(async_producer(graph, initial_state, queue))
        print(f"[BACKGROUND_LOOP] Async producer completed successfully")
        
    except Exception as e:
        print(f"[BACKGROUND_LOOP] ERROR in background loop: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        loop.close()
        print(f"[BACKGROUND_LOOP] Event loop closed")


def create_stream_generator(graph, initial_state: Dict[str, Any]) -> Generator[str, None, None]:
    """
    Create a generator that yields SSE events from the graph execution.
    
    Args:
        graph: LangGraph graph instance
        initial_state: Initial state dict for the graph
        
    Yields:
        SSE-formatted strings
    """
    print(f"[STREAM_GENERATOR] Creating stream generator")
    print(f"[STREAM_GENERATOR] Session ID: {initial_state.get('session_id')}")
    print(f"[STREAM_GENERATOR] Message: {initial_state.get('message', '')[:100]}...")
    
    # Queue for passing SSE lines from the async producer to the Flask generator
    q: _queue.Queue = _queue.Queue()
    print(f"[STREAM_GENERATOR] Created queue for SSE events")

    # Start background thread that will populate the queue
    t = threading.Thread(target=start_background_loop, args=(graph, initial_state, q))
    t.start()
    print(f"[STREAM_GENERATOR] Started background thread")

    # Yield items as they arrive from the async producer
    item_count = 0
    while True:
        item = q.get()
        if item is None:
            print(f"[STREAM_GENERATOR] Received end signal. Total items yielded: {item_count}")
            break
        item_count += 1
        print(f"[STREAM_GENERATOR] Yielding item #{item_count}: {item[:100]}...")
        yield item
