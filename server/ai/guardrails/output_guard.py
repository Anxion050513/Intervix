"""Output guard — PII masking, sensitive content filtering, and response validation."""
import re
import logging
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)


class OutputRisk(StrEnum):
    SAFE = "safe"
    PII_LEAK = "pii_leak"
    SENSITIVE = "sensitive"
    HALLUCINATION = "hallucination"


@dataclass
class OutputGuardResult:
    """Result of output guard check."""
    is_safe: bool = True
    risk_type: OutputRisk = OutputRisk.SAFE
    reason: str = ""
    sanitized_text: str = ""
    masked_items: list[dict] = field(default_factory=list)  # [{type, original, masked}]


# PII detection patterns
PII_PATTERNS = {
    "email": (
        re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        "[邮箱]",
    ),
    "phone_cn": (
        re.compile(r'\b1[3-9]\d{9}\b'),
        "[手机号]",
    ),
    "id_card_cn": (
        re.compile(r'\b\d{17}[\dXx]\b'),
        "[身份证号]",
    ),
    "ip_address": (
        re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
        "[IP地址]",
    ),
    "credit_card": (
        re.compile(r'\b(?:\d[ -]*?){13,16}\b'),
        "[银行卡号]",
    ),
}

# Sensitive content patterns (should not appear in interview output)
SENSITIVE_PATTERNS = [
    re.compile(r'(?i)\b(password|passwd|secret|token|api[_\s]?key)\s*[:：=]\s*\S+'),
    re.compile(r'(?i)(sk-[a-zA-Z0-9]{20,})'),  # OpenAI-style API keys
    re.compile(r'(?i)\b(access[_\s]?key|secret[_\s]?key)\s*[:：=]\s*\S+'),
]

# Chinese PII
CN_NAME_PATTERN = re.compile(
    r'(?:姓名|名字|我是|我叫|本人)\s*[:：]?\s*([一-龥]{2,4})'
)

# Hallucination detection: check if output contains obviously false confidence claims
HALLUCINATION_MARKERS = [
    re.compile(r'(?i)(绝对|肯定|毫无疑问|100%|百分之百)\s*(正确|对|没问题|可以|能)'),
]


class OutputGuard:
    """Output safety layer for AI-generated interview content.

    Protections:
    1. PII detection and masking (email, phone, ID card, etc.)
    2. Sensitive credential leakage prevention
    3. Basic hallucination marker detection
    4. Response length validation
    """

    MAX_OUTPUT_LENGTH = 10000

    def __init__(self):
        pass

    def mask_pii(self, text: str) -> tuple[str, list[dict]]:
        """Detect and mask personally identifiable information.

        Returns:
            Tuple of (sanitized text, list of masked items)
        """
        masked_items = []

        for pii_type, (pattern, replacement) in PII_PATTERNS.items():
            matches = pattern.findall(text)
            for match in matches:
                masked_items.append({
                    "type": pii_type,
                    "original": match,
                    "masked": replacement,
                })
            text = pattern.sub(replacement, text)

        # Chinese name detection (less aggressive — only mask clear name declarations)
        name_matches = CN_NAME_PATTERN.findall(text)
        for match in name_matches:
            if len(match) >= 2:
                masked_items.append({
                    "type": "chinese_name",
                    "original": match,
                    "masked": "[姓名]",
                })
                text = text.replace(match, "[姓名]", 1)

        return text, masked_items

    def check_sensitive(self, text: str) -> list[str]:
        """Check for sensitive credential/secret leakage."""
        issues = []
        for pattern in SENSITIVE_PATTERNS:
            if pattern.search(text):
                issues.append(f"检测到敏感凭据泄露: {pattern.pattern[:50]}...")
        return issues

    def check_hallucination(self, text: str) -> list[str]:
        """Check for hallucination markers (overconfident claims)."""
        issues = []
        for pattern in HALLUCINATION_MARKERS:
            if pattern.search(text):
                issues.append(f"检测到过度自信表述（疑似幻觉）: {pattern.pattern[:50]}...")
        return issues

    def validate(self, text: str) -> OutputGuardResult:
        """Run all output guards and return sanitized result.

        This is a synchronous method suitable for streaming response
        post-processing.
        """
        if not text or not text.strip():
            return OutputGuardResult(
                is_safe=True,
                sanitized_text="",
            )

        # Length check
        if len(text) > self.MAX_OUTPUT_LENGTH:
            logger.warning(f"Output truncated: {len(text)} > {self.MAX_OUTPUT_LENGTH}")
            text = text[:self.MAX_OUTPUT_LENGTH]

        all_issues = []
        all_masked = []

        # PII masking
        sanitized, masked = self.mask_pii(text)
        if masked:
            all_masked.extend(masked)
            all_issues.append(f"已脱敏 {len(masked)} 处个人信息")

        # Sensitive content check
        sensitive_issues = self.check_sensitive(sanitized)
        all_issues.extend(sensitive_issues)

        # Hallucination check
        halluc_issues = self.check_hallucination(sanitized)
        all_issues.extend(halluc_issues)

        is_safe = len(sensitive_issues) == 0
        risk_type = OutputRisk.SAFE
        if sensitive_issues:
            risk_type = OutputRisk.SENSITIVE
        if halluc_issues:
            risk_type = OutputRisk.HALLUCINATION
        if masked:
            # PII detected but masked = safe now
            pass

        if all_issues:
            logger.info(f"Output guard: {'; '.join(all_issues)}")

        return OutputGuardResult(
            is_safe=is_safe,
            risk_type=risk_type,
            reason="; ".join(all_issues) if all_issues else "",
            sanitized_text=sanitized,
            masked_items=all_masked,
        )

    def validate_streaming_chunk(self, chunk: str) -> str:
        """Fast guard for streaming chunks (PII check only, no full validation)."""
        if not chunk:
            return chunk
        sanitized, _ = self.mask_pii(chunk)
        return sanitized


# Global singleton instances
_input_guard = None
_output_guard = None


def get_input_guard(llm_factory=None) -> "InputGuard":
    """Get or create the global input guard instance."""
    global _input_guard
    if _input_guard is None:
        from server.ai.guardrails.input_guard import InputGuard
        _input_guard = InputGuard(llm_factory=llm_factory)
    return _input_guard


def get_output_guard() -> "OutputGuard":
    """Get or create the global output guard instance."""
    global _output_guard
    if _output_guard is None:
        _output_guard = OutputGuard()
    return _output_guard
