"""Shared adapter boundary for the portable ingest runtime."""

from .adapter_contract import (
    ADAPTER_ACTIVE_ENV,
    ADAPTER_ROOT_ENV,
    GENERIC_RUNTIME_ENV,
    AdapterError,
    configured_adapter,
    dispatch_configured_adapter,
)

__all__ = [
    "ADAPTER_ACTIVE_ENV",
    "ADAPTER_ROOT_ENV",
    "GENERIC_RUNTIME_ENV",
    "AdapterError",
    "configured_adapter",
    "dispatch_configured_adapter",
]
