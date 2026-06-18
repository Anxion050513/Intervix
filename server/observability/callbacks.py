"""LangChain callback integration with async-safe trace context.

Uses a custom BaseCallbackHandler (from langchain_core) that translates
LangChain LLM events into langfuse generations via the native SDK.
This avoids the langfuse→langchain callback compatibility issues between
langfuse 2.x and langchain 1.x.
"""

import contextvars
import logging
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger(__name__)

# === Async-safe trace context via contextvars ===

_trace_session_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_session_id", default=""
)
_trace_skill_module: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_skill_module", default=""
)
_trace_question_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_question_id", default=""
)
_trace_phase: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_phase", default="unknown"
)


class TraceContext:
    """Async-safe trace metadata storage backed by contextvars.

    Usage:
        TraceContext.set(session_id="abc", skill_module="technical_qa", phase="generate")
        try:
            ...  # LLM calls here automatically pick up this context
        finally:
            TraceContext.clear()
    """

    @classmethod
    def set(
        cls,
        *,
        session_id: str = "",
        skill_module: str = "",
        question_id: str = "",
        phase: str = "",
    ):
        """Set trace context for the current async task."""
        if session_id:
            _trace_session_id.set(session_id)
        if skill_module:
            _trace_skill_module.set(skill_module)
        if question_id:
            _trace_question_id.set(question_id)
        if phase:
            _trace_phase.set(phase)

    @classmethod
    def get(cls) -> dict:
        """Get current trace context as a dict."""
        return {
            "session_id": _trace_session_id.get(),
            "skill_module": _trace_skill_module.get(),
            "question_id": _trace_question_id.get(),
            "phase": _trace_phase.get(),
        }

    @classmethod
    def clear(cls):
        """Reset all trace context fields to defaults."""
        _trace_session_id.set("")
        _trace_skill_module.set("")
        _trace_question_id.set("")
        _trace_phase.set("unknown")


# === LangFuse Tracer (custom BaseCallbackHandler) ===


class LangFuseTracer(BaseCallbackHandler):
    """Translates LangChain LLM callbacks → langfuse generations.

    Extends BaseCallbackHandler so LangChain's callback system recognizes it.
    Each LLM call becomes a langfuse Generation. All generations
    within the same session share the same trace_id (= session_id).
    """

    def __init__(self):
        self._pending: dict[UUID, object] = {}  # run_id → StatefulGenerationClient

    @property
    def client(self):
        """Lazy-access the langfuse client (may not be initialized at import time)."""
        from server.observability.langfuse_client import get_langfuse_client
        mgr = get_langfuse_client()
        return mgr.client if mgr.enabled else None

    @property
    def ctx(self) -> dict:
        """Current trace context."""
        return TraceContext.get()

    # === LangChain callback interface ===

    def _create_generation(self, run_id: UUID, model_name: str, input_data):
        """Create a langfuse generation for the current trace context."""
        cl = self.client
        if cl is None:
            return

        ctx = self.ctx
        session_id = ctx.get("session_id", "")
        phase = ctx.get("phase", "unknown")
        skill = ctx.get("skill_module", "")

        # Build a readable name
        name_parts = [phase]
        if skill:
            name_parts.append(skill)
        name = "-".join(name_parts)

        try:
            gen = cl.generation(
                trace_id=session_id if session_id else None,
                name=name,
                model=model_name,
                input=input_data,
                metadata={
                    "session_id": session_id,
                    "skill_module": skill,
                    "question_id": ctx.get("question_id", ""),
                    "phase": phase,
                },
                tags=[t for t in [phase, skill] if t],
            )
            self._pending[run_id] = gen
        except Exception as e:
            logger.debug("LangFuse create_generation failed: %s", e)

    def _end_generation(self, run_id: UUID, output: str, tok: dict | None = None, error: str | None = None):
        """Update and end a pending generation, then flush to langfuse."""
        gen = self._pending.pop(run_id, None)
        if gen is None:
            return
        try:
            usage = {}
            if tok:
                usage["input"] = tok.get("prompt_tokens", 0) or 0
                usage["output"] = tok.get("completion_tokens", 0) or 0
                if tok.get("total_tokens"):
                    usage["total"] = tok["total_tokens"]

            if error:
                gen.update(status_message=error[:500], level="ERROR")
            else:
                gen.update(output=output, usage_details=usage if usage else None)
            gen.end()

            # Flush immediately so data appears in dashboard without delay
            cl = self.client
            if cl:
                cl.flush()
        except Exception as e:
            logger.debug("LangFuse end_generation failed: %s", e)

    # ---- Chat model callbacks (langchain 1.x uses these for ChatOpenAI) ----

    def on_chat_model_start(
        self,
        serialized: dict,
        messages: list,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict | None = None,
        **kwargs,
    ):
        """Called before every ChatOpenAI call (langchain 1.x)."""
        llm_kwargs = serialized.get("kwargs", {})
        model_name = llm_kwargs.get("model", llm_kwargs.get("model_name", "unknown"))
        # Convert messages to a serializable form
        input_data = []
        for msg_list in messages:
            for m in msg_list:
                if hasattr(m, "content"):
                    input_data.append({"role": getattr(m, "type", "unknown"), "content": str(m.content)[:500]})
                else:
                    input_data.append(str(m)[:500])
        self._create_generation(run_id, model_name, input_data)

    def on_llm_end(
        self,
        response,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs,
    ):
        """Called after every LLM call."""
        output = ""
        if response.generations and response.generations[0]:
            first_gen = response.generations[0][0]
            if hasattr(first_gen, "message") and first_gen.message:
                output = getattr(first_gen.message, "content", "") or str(first_gen.message)
            elif hasattr(first_gen, "text"):
                output = first_gen.text or ""

        tok = (response.llm_output or {}).get("token_usage", {})
        self._end_generation(run_id, output, tok if isinstance(tok, dict) else None)

    def on_llm_error(
        self,
        error,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs,
    ):
        """Called when an LLM call fails."""
        self._end_generation(run_id, "", error=str(error))

    # ---- Legacy on_llm_start (for non-chat models / older langchain) ----

    def on_llm_start(
        self,
        serialized: dict,
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict | None = None,
        **kwargs,
    ):
        """Called before non-chat LLM calls (legacy support)."""
        llm_kwargs = serialized.get("kwargs", {})
        model_name = llm_kwargs.get("model", llm_kwargs.get("model_name", "unknown"))
        self._create_generation(run_id, model_name, prompts)


# === Module-level singleton tracer ===

_tracer: LangFuseTracer | None = None


def get_langfuse_callback():
    """Get a LangFuseTracer callback handler, or None if LangFuse is disabled.

    Returns the same singleton instance so LangChain always uses the
    same handler across all LLM calls.
    """
    from server.observability.langfuse_client import is_langfuse_enabled

    if not is_langfuse_enabled():
        return None

    global _tracer
    if _tracer is None:
        _tracer = LangFuseTracer()
    return _tracer
