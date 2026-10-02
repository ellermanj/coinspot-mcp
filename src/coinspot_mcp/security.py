"""Least-privilege and runtime guards for the CoinSpot MCP server."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
from contextvars import ContextVar
from typing import Any

from coinspot_mcp.client import CoinspotError, env_flag

AUDIT_LOGGER = logging.getLogger("coinspot_mcp.audit")

# Request-scoped caller metadata for auditability (set by Lambda/HTTP entrypoint).
mcp_caller_id: ContextVar[str | None] = ContextVar("mcp_caller_id", default=None)
mcp_source_ip: ContextVar[str | None] = ContextVar("mcp_source_ip", default=None)

# Params that must never appear in audit logs or model-facing errors.
_SENSITIVE_PARAM_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "coinspot_api_key",
        "coinspot_api_secret",
        "secret",
        "password",
        "token",
        "confirm_token",
        "sign",
        "key",
    }
)

_REDACT_PATTERNS = (
    re.compile(r"(?i)(api[_-]?secret|secret|password|token)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(sign|key)\s*[:=]\s*[0-9a-f]{16,}"),
)


def configure_audit_logging() -> None:
    """Ensure the audit logger emits to stderr if the app has no handlers yet."""
    if AUDIT_LOGGER.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    AUDIT_LOGGER.addHandler(handler)
    AUDIT_LOGGER.setLevel(logging.INFO)
    AUDIT_LOGGER.propagate = False


def redact_value(value: Any, *, key: str | None = None) -> Any:
    if key and key.lower() in _SENSITIVE_PARAM_KEYS:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {k: redact_value(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, str) and len(value) > 120:
        return value[:40] + "…[truncated]"
    return value


def sanitize_error_message(message: str) -> str:
    cleaned = message.strip() or "CoinSpot request failed"
    for pattern in _REDACT_PATTERNS:
        cleaned = pattern.sub(r"\1=[REDACTED]", cleaned)
    if len(cleaned) > 240:
        cleaned = cleaned[:240] + "…"
    return cleaned


def token_fingerprint(token: str) -> str:
    """Stable non-reversible identifier for audit logs."""
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return digest[:16]


def configured_mcp_auth_tokens() -> list[str]:
    """Return configured MCP bearer tokens (supports multi-user comma lists)."""
    tokens: list[str] = []
    single = os.getenv("COINSPOT_MCP_AUTH_TOKEN", "").strip()
    if single:
        tokens.append(single)
    multi = os.getenv("COINSPOT_MCP_AUTH_TOKENS", "").strip()
    if multi:
        tokens.extend(item.strip() for item in multi.split(",") if item.strip())
    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            unique.append(token)
    return unique


def verify_mcp_bearer_token(provided: str | None) -> str | None:
    """Constant-time verify against configured tokens.

    Compares SHA-256 digests so length differences cannot leak via compare_digest.
    Always evaluates every configured token to reduce multi-token timing bias.

    Returns a token fingerprint on success, otherwise None.
    """
    expected_tokens = configured_mcp_auth_tokens()
    if not expected_tokens:
        return None
    candidate = (provided or "").strip()
    if not candidate:
        return None

    candidate_digest = hashlib.sha256(candidate.encode("utf-8")).digest()
    matched_fingerprint: str | None = None
    for expected in expected_tokens:
        expected_digest = hashlib.sha256(expected.encode("utf-8")).digest()
        if hmac.compare_digest(candidate_digest, expected_digest):
            # Keep scanning remaining tokens; first match wins for fingerprint.
            if matched_fingerprint is None:
                matched_fingerprint = token_fingerprint(expected)
    return matched_fingerprint


def audit_event(
    tool_name: str,
    *,
    outcome: str,
    params: dict[str, Any] | None = None,
    detail: str | None = None,
) -> None:
    configure_audit_logging()
    safe_params = redact_value(params or {})
    parts = [f"tool={tool_name}", f"outcome={outcome}", f"params={safe_params}"]
    caller = mcp_caller_id.get()
    if caller:
        parts.append(f"caller={caller}")
    source_ip = mcp_source_ip.get()
    if source_ip:
        parts.append(f"source_ip={source_ip}")
    if detail:
        parts.append(f"detail={sanitize_error_message(detail)}")
    AUDIT_LOGGER.info(" ".join(parts))


def require_destructive_confirmation(confirm_token: str | None) -> None:
    """Require an exact match for destructive calls when a confirm token is configured."""
    expected = os.getenv("COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN", "").strip()
    if not expected:
        raise CoinspotError(
            "Destructive action denied: COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN is not configured."
        )
    provided = (confirm_token or "").strip()
    if not provided or len(provided) != len(expected):
        raise CoinspotError(
            "Destructive action denied: confirm_token is missing or invalid."
        )
    if not hmac.compare_digest(provided, expected):
        raise CoinspotError(
            "Destructive action denied: confirm_token is missing or invalid."
        )


def destructive_confirm_configured() -> bool:
    return bool(os.getenv("COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN", "").strip())


def _optional_float_env(name: str) -> float | None:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise CoinspotError(f"Invalid {name} value; expected a number.") from exc
    if value <= 0:
        raise CoinspotError(f"{name} must be greater than zero.")
    return value


def enforce_order_amount(amount: float | int | str) -> None:
    limit = _optional_float_env("COINSPOT_MAX_ORDER_AMOUNT")
    if limit is None:
        return
    try:
        numeric = float(amount)
    except (TypeError, ValueError) as exc:
        raise CoinspotError("Order amount must be numeric.") from exc
    if numeric > limit:
        raise CoinspotError(
            f"Order amount {numeric} exceeds COINSPOT_MAX_ORDER_AMOUNT={limit}."
        )


def enforce_withdraw_amount(amount: float | int | str) -> None:
    limit = _optional_float_env("COINSPOT_MAX_WITHDRAW_AMOUNT")
    if limit is None:
        return
    try:
        numeric = float(amount)
    except (TypeError, ValueError) as exc:
        raise CoinspotError("Withdrawal amount must be numeric.") from exc
    if numeric > limit:
        raise CoinspotError(
            f"Withdrawal amount {numeric} exceeds COINSPOT_MAX_WITHDRAW_AMOUNT={limit}."
        )


def enforce_withdraw_address(address: str) -> None:
    raw = os.getenv("COINSPOT_WITHDRAW_ADDRESS_ALLOWLIST", "").strip()
    if not raw:
        return
    allowed = {item.strip() for item in raw.split(",") if item.strip()}
    if address.strip() not in allowed:
        raise CoinspotError(
            "Withdrawal address is not in COINSPOT_WITHDRAW_ADDRESS_ALLOWLIST."
        )


def trading_enabled() -> bool:
    return env_flag("COINSPOT_ALLOW_TRADING")


def withdrawals_enabled() -> bool:
    return env_flag("COINSPOT_ALLOW_WITHDRAWALS")
