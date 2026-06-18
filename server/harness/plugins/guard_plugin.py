"""Guard plugin — logs and tracks all guardrail events."""
import logging

from server.harness.hooks import InterviewHooks

logger = logging.getLogger(__name__)


class GuardPlugin:
    """Harness plugin that listens to guardrail events and logs incidents.

    In production, this would also:
    - Send alerts for repeated injection attempts
    - Feed into a security dashboard
    - Trigger rate limiting on malicious users
    """

    name = "guard_plugin"

    async def on_input_blocked(
        self,
        session_id: str,
        risk_type: str,
        reason: str,
        risk_score: float,
        input_preview: str,
    ):
        """Called when input guard blocks a user's answer."""
        logger.warning(
            f"[GUARD] Input blocked in session {session_id}: "
            f"type={risk_type}, score={risk_score:.2f}, reason={reason}"
        )
        # Log a preview of the blocked input (truncated)
        preview = input_preview[:200] + "..." if len(input_preview) > 200 else input_preview
        logger.info(f"[GUARD] Blocked input preview: {preview}")

    async def on_output_sanitized(
        self,
        session_id: str,
        risk_type: str,
        reason: str,
        masked_count: int,
    ):
        """Called when output guard sanitizes generated content."""
        if masked_count > 0 or risk_type != "safe":
            logger.info(
                f"[GUARD] Output sanitized in session {session_id}: "
                f"type={risk_type}, masked={masked_count} items, reason={reason}"
            )
