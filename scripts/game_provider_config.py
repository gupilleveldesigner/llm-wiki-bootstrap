"""Shared, dependency-free configuration contract for optional Game providers."""
from __future__ import annotations

import re
from typing import Any

PROVIDER_SCHEMA_VERSION = 1
PROVIDER_SLOTS = ("code_intelligence", "knowledge_graph")
KNOWN_PROVIDER_SLOTS = {"codegraph": "code_intelligence", "graphify": "knowledge_graph"}


def normalize_providers(value: Any) -> dict[str, str | None]:
    if not isinstance(value, dict):
        raise ValueError("providers must be an object")
    if set(value) - set(PROVIDER_SLOTS):
        raise ValueError("providers contains an unsupported slot")
    result: dict[str, str | None] = dict.fromkeys(PROVIDER_SLOTS)
    for slot, provider in value.items():
        if provider is not None:
            if not isinstance(provider, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", provider):
                raise ValueError(f"providers.{slot} must be null or a lowercase provider identifier")
            if provider in KNOWN_PROVIDER_SLOTS and KNOWN_PROVIDER_SLOTS[provider] != slot:
                raise ValueError(f"provider {provider} does not support slot {slot}")
        result[slot] = provider
    return result


def resolve_provider_settings(config: dict[str, Any], previous: Any = None) -> dict[str, Any]:
    """Omission preserves selections; explicit null disables; unknown IDs stay inert."""
    if previous is None:
        previous = {}
    if not isinstance(previous, dict):
        raise ValueError("game_project must be an object")
    for source in (previous, config):
        version = source.get("provider_schema_version", PROVIDER_SCHEMA_VERSION)
        if type(version) is not int or version != PROVIDER_SCHEMA_VERSION:
            raise ValueError("unsupported provider_schema_version; expected 1")
    providers = normalize_providers(previous.get("providers", {}))
    if "providers" in config:
        normalize_providers(config["providers"])
        providers.update(config["providers"])
    return {"provider_schema_version": PROVIDER_SCHEMA_VERSION, "providers": providers}
