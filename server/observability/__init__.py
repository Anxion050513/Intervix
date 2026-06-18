"""Observability module — LangFuse tracing + Eval framework.

All features gracefully degrade when LangFuse credentials are not configured.
"""

from server.observability.langfuse_client import (
    LangFuseClientManager,
    get_langfuse_client,
    is_langfuse_enabled,
)
from server.observability.callbacks import (
    TraceContext,
    get_langfuse_callback,
)

__all__ = [
    "LangFuseClientManager",
    "get_langfuse_client",
    "is_langfuse_enabled",
    "TraceContext",
    "get_langfuse_callback",
    "EvalRunner",
    "router",
]

