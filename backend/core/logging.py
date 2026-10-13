import logging
import re
import sys
from typing import Any
from backend.core.config import get_settings

# Sensitive tokens scrubbing patterns
_SENSITIVE_PATTERNS = [
    (re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(api[_-]?key[\"']?\s*[:=]\s*[\"']?)[A-Za-z0-9\-._~+/]{8,}", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(nvapi-[A-Za-z0-9\-._~+/]+)", re.IGNORECASE), r"[REDACTED_NVIDIA_KEY]"),
    (re.compile(r"(gsk_[A-Za-z0-9\-._~+/]+)", re.IGNORECASE), r"[REDACTED_GROQ_KEY]"),
    (re.compile(r"(sk-[A-Za-z0-9\-._~+/]+)", re.IGNORECASE), r"[REDACTED_OPENAI_KEY]"),
    (re.compile(r"(tvly-[A-Za-z0-9\-._~+/]+)", re.IGNORECASE), r"[REDACTED_TAVILY_KEY]"),
]

class SanitizedFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        for pattern, replacement in _SENSITIVE_PATTERNS:
            msg = pattern.sub(replacement, msg)
        return msg

def setup_logging() -> None:
    settings = get_settings()
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = SanitizedFormatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
