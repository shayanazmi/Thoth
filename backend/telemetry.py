import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger("ThothTelemetry")

try:
    from deepeval.tracing import observe, update_current_span, trace_manager
    from deepeval.tracing.tracing import EvalMode
    DEEPEVAL_AVAILABLE = True
except ImportError:
    DEEPEVAL_AVAILABLE = False
    trace_manager = None
    EvalMode = None

    def observe(*args, **kwargs):
        """Fallback no-op decorator when deepeval is not installed."""
        def decorator(func):
            return func
        return decorator

    def update_current_span(*args, **kwargs):
        """Fallback no-op function when deepeval is not installed."""
        pass


def enable_local_tracing() -> None:
    """Enables local offline in-memory tracing in DeepEval without requiring Confident AI API keys."""
    if DEEPEVAL_AVAILABLE and trace_manager and EvalMode:
        trace_manager.eval_session.mode = EvalMode.ITERATOR_ASYNC
        logger.info("[TELEMETRY] DeepEval local in-memory tracing enabled (EvalMode.ITERATOR_ASYNC).")


def clear_local_traces() -> None:
    """Clears all captured in-memory traces."""
    if DEEPEVAL_AVAILABLE and trace_manager:
        trace_manager.clear_traces()
        # Reset eval session queue if needed
        if hasattr(trace_manager, "eval_session") and trace_manager.eval_session:
            trace_manager.eval_session.traces_to_evaluate.clear()
            trace_manager.eval_session.pending_traces.clear()


def get_local_traces() -> List[Any]:
    """Retrieves all captured traces."""
    if DEEPEVAL_AVAILABLE and trace_manager:
        return trace_manager.get_all_traces_dict()
    return []


def get_telemetry_status() -> Dict[str, Any]:
    """Returns telemetry, circuit breaker, and LLM configuration status."""
    import os
    from backend.dispatcher import default_dispatcher, scholarly_dispatcher, s2_dispatcher

    primary_model = os.getenv("NVIDIA_PRIMARY_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
    fallback_model = os.getenv("GROQ_FALLBACK_MODEL", "groq/llama-3.3-70b-versatile")
    
    return {
        "status": "online",
        "deepeval_tracing": DEEPEVAL_AVAILABLE,
        "circuit_breaker_state": default_dispatcher._state,
        "scholarly_breaker_state": scholarly_dispatcher._state,
        "s2_breaker_state": s2_dispatcher._state,
        "primary_provider": "NVIDIA AI Foundation NIM",
        "primary_model": primary_model,
        "fallback_provider": "Groq Cloud / OpenAI",
        "fallback_model": fallback_model,
    }
