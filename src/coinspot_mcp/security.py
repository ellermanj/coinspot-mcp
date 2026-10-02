"""Least-privilege and runtime guards for the CoinSpot MCP server."""

from __future__ import annotations

import hmac
import logging
import os
import re
from typing import Any

from coinspot_mcp.client import CoinspotError, env_flag

AUDIT_LOGGER = logging.getLogger("coinspot_mcp.audit")

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
    if detail:
        parts.append(f"detail={sanitize_error_message(detail)}")
    AUDIT_LOGGER.info(" ".join(parts))


def require_destructive_confirmation(confirm_token: str | None) -> None:
    """If a confirm token is configured, require an exact match for destructive calls."""
    expected = os.getenv("COINSPOT_DESTRUCTIVE_CONFIRM_TOKEN", "").strip()
    if not expected:
        return
    provided = (confirm_token or "").strip()
    if not provided or not hmac.compare_digest(provided, expected):
        raise CoinspotError(
            "Destructive action denied: confirm_token is missing or invalid."
        )


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
