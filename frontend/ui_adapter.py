import threading
import time
from typing import Callable, Optional, Dict, Any, List
from backend.pipeline import stream_research_pipeline, stream_followup_turn

NODE_LABEL_MAP = {
    "search": "Search",
    "scrape": "Reader",
    "writer": "Writer",
    "verifier": "Verifier",
    "critic": "Critic",
    "mindmap": "Mind Map",
    "follow_up": "Follow-Up"
}

NODE_ORDER = ["search", "scrape", "writer", "verifier", "critic", "mindmap", "follow_up"]

class ResearchPipelineRunner:
    SCHEMA_VERSION = 2  # Bump when adding/removing instance attributes

    def __init__(self):
        self._schema_version = self.SCHEMA_VERSION
        self.thread: Optional[threading.Thread] = None
        self.cancel_event = threading.Event()
        self.is_active = False
        self.is_completed = False
        self.error: Optional[Exception] = None
        
        self.active_node: str = ""
        self.node_statuses: List[str] = ["pending"] * 7
        self.node_durations: Dict[str, float] = {}
        self.node_logs: Dict[str, str] = {
            "search": "",
            "scrape": "",
            "writer": "",
            "verifier": "",
            "critic": "",
            "mindmap": "",
            "follow_up": ""
        }
        self.final_state: Dict[str, Any] = {}
        self.run_start_time: float = 0.0
        self.current_session_id: str = ""
        
        # Follow-up turn runner state
        self.is_followup_active = False
        self.active_followup_event = ""
        self.active_followup_payload: Dict[str, Any] = {}
        self.followup_completed = False
        self.latest_followup_payload: Optional[Dict[str, Any]] = None

    def reset(self):
        self.active_node = "search"
        self.node_statuses = ["active"] + ["pending"] * 6
        self.node_durations = {}
        self.node_logs = {k: "" for k in self.node_logs}
        self.final_state = {}
        self.is_completed = False
        self.error = None
        self.run_start_time = time.time()
        self.is_followup_active = False
        self.active_followup_event = ""
        self.active_followup_payload = {}
        self.followup_completed = False
        self.latest_followup_payload = None

    def start(
        self,
        topic: str,
        role: str = "senior academic researcher",
        tone: str = "formal and analytical",
        language: str = "English",
        scrape_top_n: int = 2,
        min_score: float = 6.5,
        max_retries: int = 2,
        session_id: Optional[str] = None,
        on_node_update: Optional[Callable[[str, Dict[str, Any], Dict[str, Any], Dict[str, float]], None]] = None,
        on_complete: Optional[Callable[[Dict[str, Any], Dict[str, float]], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ):
        """Starts the initial pipeline execution in a non-blocking background thread."""
        if self.is_active or self.is_followup_active:
            raise RuntimeError("Pipeline or follow-up is already running!")
            
        import uuid
        self.current_session_id = session_id or f"sess_{uuid.uuid4().hex[:12]}"
        self.cancel_event.clear()
        self.is_active = True
        self.reset()
        
        def _worker():
            last_node_time = time.time()
            try:
                for node_name, update, current_state in stream_research_pipeline(
                    topic=topic,
                    role=role,
                    tone=tone,
                    language=language,
                    scrape_top_n=scrape_top_n,
                    min_score=min_score,
                    max_retries=max_retries,
                    cancel_event=self.cancel_event
                ):
                    now = time.time()
                    duration = now - last_node_time
                    label = NODE_LABEL_MAP.get(node_name, node_name)
                    self.node_durations[label] = round(duration, 2)
                    last_node_time = now

                    # Update internal runner states
                    self.active_node = node_name
                    if node_name in NODE_ORDER:
                        idx = NODE_ORDER.index(node_name)
                        self.node_statuses[idx] = "done"
                        if idx + 1 < len(self.node_statuses):
                            self.node_statuses[idx + 1] = "active"

                    # Capture feedback / loopback retries
                    if node_name == "verifier" and update.get("verifier_feedback"):
                        self.node_statuses[2] = "retry"
                    elif node_name == "critic" and current_state.get("score", 0.0) < current_state.get("min_score", 6.5) and current_state.get("attempt", 0) <= current_state.get("max_retries", 2):
                        self.node_statuses[2] = "retry"

                    # Accumulate logs
                    if "search_results" in update and update["search_results"]:
                        self.node_logs["search"] = update["search_results"]
                    if "scraped_content" in update and update["scraped_content"]:
                        self.node_logs["scrape"] = update["scraped_content"]
                    if "report" in update and update["report"]:
                        self.node_logs["writer"] = update["report"]
                    if "verifier_feedback" in update:
                        fb = update["verifier_feedback"]
                        self.node_logs["verifier"] = fb if fb else "✓ All factual claims verified against scraped sources."
                    if "feedback" in update and update["feedback"]:
                        self.node_logs["critic"] = update["feedback"]
                    if "mindmap" in update and update["mindmap"]:
                        self.node_logs["mindmap"] = f"Generated {len(update['mindmap'].get('nodes', []))} nodes, {len(update['mindmap'].get('edges', []))} edges."

                    self.final_state = current_state

                    if on_node_update:
                        try:
                            on_node_update(node_name, update, current_state, self.node_durations)
                        except Exception as cb_err:
                            print(f"[UI ADAPTER] Callback error: {cb_err}")

                if not self.cancel_event.is_set():
                    self.node_statuses = ["done"] * 7
                    self.active_node = "done"
                    self.is_completed = True
                    
                    # Persist session & report to SQLite database
                    try:
                        from backend.memory.db import save_session, save_report
                        sess_id = self.current_session_id
                        top = self.final_state.get("topic", topic)
                        rep_content = self.final_state.get("report", "")
                        sc = self.final_state.get("score", 0.0)
                        v_fb = self.final_state.get("verifier_feedback", "")
                        mm = self.final_state.get("mindmap", {})
                        save_session(session_id=sess_id, title=top, summary=rep_content[:300])
                        if rep_content:
                            rep_id = f"rep_{uuid.uuid4().hex[:10]}"
                            save_report(report_id=rep_id, session_id=sess_id, topic=top, content=rep_content, score=sc, verifier_feedback=v_fb, mindmap=mm)
                    except Exception as db_err:
                        print(f"[UI ADAPTER DB PERSIST ERROR] {db_err}")

                    if on_complete:
                        try:
                            on_complete(self.final_state, self.node_durations)
                        except Exception as comp_err:
                            print(f"[UI ADAPTER] Complete callback error: {comp_err}")
            except Exception as e:
                self.error = e
                print(f"[UI ADAPTER] Pipeline execution error: {e}")
                if on_error:
                    try:
                        on_error(e)
                    except Exception:
                        pass
            finally:
                self.is_active = False

        self.thread = threading.Thread(target=_worker, daemon=True)
        
        try:
            from streamlit.runtime.scriptrunner import add_script_run_ctx
            add_script_run_ctx(self.thread)
        except Exception:
            pass
            
        self.thread.start()

    def start_followup(
        self,
        current_state: Dict[str, Any],
        user_query: str,
        mode_override: str = "auto",
        on_event: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        on_complete: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ):
        """Executes a multi-turn follow-up question asynchronously."""
        if self.is_active or self.is_followup_active:
            raise RuntimeError("A research pipeline or follow-up is already running!")
            
        self.cancel_event.clear()
        self.is_followup_active = True
        self.followup_completed = False
        self.latest_followup_payload = None
        self.error = None
        
        def _followup_worker():
            try:
                latest_payload = {}
                for event_name, payload in stream_followup_turn(
                    current_state=current_state,
                    user_query=user_query,
                    mode_override=mode_override,
                    cancel_event=self.cancel_event
                ):
                    self.active_followup_event = event_name
                    self.active_followup_payload = payload
                    latest_payload = payload
                    if on_event:
                        try:
                            on_event(event_name, payload)
                        except Exception as e:
                            print(f"[UI ADAPTER FOLLOWUP] Event callback error: {e}")
                            
                self.latest_followup_payload = latest_payload
                self.followup_completed = True
                
                if on_complete:
                    try:
                        on_complete(latest_payload)
                    except Exception as e:
                        print(f"[UI ADAPTER FOLLOWUP] Complete callback error: {e}")
            except Exception as e:
                self.error = e
                print(f"[UI ADAPTER FOLLOWUP] Error: {e}")
                if on_error:
                    try:
                        on_error(e)
                    except Exception:
                        pass
            finally:
                self.is_followup_active = False

        self.thread = threading.Thread(target=_followup_worker, daemon=True)
        try:
            from streamlit.runtime.scriptrunner import add_script_run_ctx
            add_script_run_ctx(self.thread)
        except Exception:
            pass
        self.thread.start()

    def consume_followup_payload(self) -> Optional[Dict[str, Any]]:
        """Safely consumes the completed follow-up result in the main Streamlit thread."""
        if self.followup_completed and self.latest_followup_payload:
            payload = dict(self.latest_followup_payload)
            self.followup_completed = False
            self.latest_followup_payload = None
            return payload
        return None

    def cancel(self):
        """Sets the cancellation flag."""
        self.cancel_event.set()
        print("[UI ADAPTER] Cancel event set by user.")

    def is_running(self) -> bool:
        return self.is_active or self.is_followup_active


# ==============================================================================
# WORKSPACE DATA BRIDGE HELPERS
# ==============================================================================

def list_stored_sessions(limit: int = 50) -> List[Dict[str, Any]]:
    """Fetches past research sessions from SQLite."""
    try:
        from backend.memory.db import list_sessions
        return list_sessions(limit=limit)
    except Exception as e:
        print(f"[UI ADAPTER] Error listing sessions: {e}")
        return []

def list_stored_reports(limit: int = 50) -> List[Dict[str, Any]]:
    """Fetches stored research reports from SQLite."""
    try:
        from backend.memory.db import list_reports
        return list_reports(limit=limit)
    except Exception as e:
        print(f"[UI ADAPTER] Error listing reports: {e}")
        return []

def get_stored_report_by_id(report_id: str) -> Optional[Dict[str, Any]]:
    """Fetches a specific stored report by ID."""
    try:
        from backend.memory.db import get_report
        return get_report(report_id)
    except Exception as e:
        print(f"[UI ADAPTER] Error fetching report {report_id}: {e}")
        return None

def search_memory_vault(query: str, top_k: int = 8) -> List[Dict[str, Any]]:
    """Performs real-time Reciprocal Rank Fusion hybrid search on the Obsidian vault."""
    try:
        from backend.memory.index import hybrid_search
        return hybrid_search(query=query, top_k=top_k)
    except Exception as e:
        print(f"[UI ADAPTER] Vault search error: {e}")
        return []

def list_vault_notes(note_type: Optional[str] = None) -> List[str]:
    """Lists note IDs in the Obsidian vault, optionally filtered by type."""
    try:
        from backend.memory.vault import list_notes
        return list_notes(note_type=note_type)
    except Exception as e:
        print(f"[UI ADAPTER] Error listing vault notes: {e}")
        return []

def read_vault_note(note_id: str) -> Optional[Dict[str, Any]]:
    """Reads a note's frontmatter and content from the Obsidian vault."""
    try:
        from backend.memory.vault import read_note
        return read_note(note_id)
    except Exception as e:
        print(f"[UI ADAPTER] Error reading vault note {note_id}: {e}")
        return None

def traverse_vault_graph(start_note: str, relation: Optional[str] = None, max_depth: int = 2) -> List[Dict[str, Any]]:
    """Traverses knowledge graph edges from a start note."""
    try:
        from backend.memory.graph import traverse
        return traverse(start_note=start_note, relation=relation, max_depth=max_depth)
    except Exception as e:
        print(f"[UI ADAPTER] Error traversing graph for {start_note}: {e}")
        return []

def get_telemetry_status() -> Dict[str, Any]:
    """Fetches live telemetry and health status from backend components."""
    import os
    from backend.dispatcher import default_dispatcher
    
    cb_state = default_dispatcher.state if hasattr(default_dispatcher, "state") else "CLOSED"
    time_until_retry = max(0.0, getattr(default_dispatcher, "_last_failure_time", 0.0) + getattr(default_dispatcher, "cooloff_seconds", 30.0) - time.time()) if cb_state == "OPEN" else 0.0
    
    has_nvidia = bool(os.getenv("NVIDIA_API_KEY"))
    has_groq = bool(os.getenv("GROQ_API_KEY"))
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    has_tavily = bool(os.getenv("TAVILY_API_KEY"))
    
    primary_provider = "NVIDIA NIM (Nemotron-30B & Llama-8B)" if has_nvidia else "Unconfigured"
    fallback_provider = "Groq (Llama-3.3-70B)" if has_groq else ("OpenAI Compatible" if has_openai else "None")
    
    # Check database size
    db_size_kb = 0
    if os.path.exists("store.db"):
        db_size_kb = round(os.path.getsize("store.db") / 1024, 1)
        
    vault_notes_count = len(list_vault_notes())
    
    return {
        "circuit_breaker_state": cb_state,
        "circuit_breaker_cooloff": round(time_until_retry, 1),
        "primary_provider": primary_provider,
        "fallback_provider": fallback_provider,
        "scholarly_sources": ["arXiv", "OpenAlex", "Semantic Scholar"],
        "web_search_available": has_tavily,
        "db_size_kb": db_size_kb,
        "vault_notes_count": vault_notes_count,
        "concurrency_limit": getattr(default_dispatcher, "max_concurrent", 3)
    }

