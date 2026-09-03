#!/usr/bin/env python3
"""Plan scoped, optional provider reads. Never connect, execute, index or write."""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path, PureWindowsPath
from typing import Any

from game_provider_config import PROVIDER_SLOTS, resolve_provider_settings
from game_trace import parse_code_ref, project_root_from_manifest

PROVIDER_RUNTIME_VERSION = 1
MAX_INVENTORY_BYTES = 1024 * 1024
MAX_TOOLS = 128
MAX_QUERY_LENGTH = 4096
REGISTRY = {
    "codegraph": {"tool": "codegraph_symbol_search", "query_field": "query", "limits": {"limit": 8, "compact": True}},
    "graphify": {"tool": "query_graph", "query_field": "question", "limits": {"token_budget": 2000}},
}
INTENTS = {"WHAT": "knowledge_graph", "HOW": "code_intelligence", "WHY": None}
FALLBACKS = {
    "WHAT": "Read the Wiki index and relevant documents; inspect project files for broader relationships.",
    "HOW": "Inspect current live files, use targeted text search and tests, and consult game_trace links.",
    "WHY": "Read canonical Wiki specs, implementation checks, validation evidence and decisions; report missing evidence.",
}
SCHEMA_METADATA = {"title", "description", "default", "examples", "$schema"}
SCALAR_RULES = {"type", "enum", "minimum", "maximum", "minLength", "maxLength"}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def read_inventory(path: Path | None) -> tuple[dict[str, Any], str | None]:
    if path is None:
        return {}, None
    try:
        with path.open("rb") as stream:
            content = stream.read(MAX_INVENTORY_BYTES + 1)
        if len(content) > MAX_INVENTORY_BYTES:
            return {}, "inventory_too_large"
        value = json.loads(content, object_pairs_hook=_unique_object)
        if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
            return {}, "unsupported_inventory"
        if not isinstance(value.get("providers"), dict):
            return {}, "invalid_inventory"
        return value["providers"], None
    except (OSError, UnicodeError, ValueError, RecursionError):
        return {}, "invalid_inventory"


def _scalar_shape(schema: Any) -> bool:
    if not isinstance(schema, dict) or set(schema) - SCHEMA_METADATA - SCALAR_RULES:
        return False
    kind = schema.get("type")
    if kind not in ("string", "integer", "number", "boolean"):
        return False
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        return False
    for key in ("minimum", "maximum", "minLength", "maxLength"):
        if key not in schema:
            continue
        bound = schema[key]
        if key in ("minLength", "maxLength"):
            if kind != "string" or type(bound) is not int or bound < 0:
                return False
        elif (kind not in ("integer", "number") or type(bound) not in (int, float)
              or (type(bound) is float and not math.isfinite(bound))):
            return False
    return True


def _accepts(value: Any, schema: dict[str, Any]) -> bool:
    types = {"string": (str,), "integer": (int,), "number": (int, float), "boolean": (bool,)}
    if not _scalar_shape(schema) or type(value) not in types[schema["type"]]:
        return False
    if type(value) is float and not math.isfinite(value):
        return False
    if "enum" in schema and not any(
        (type(item) is type(value) or (type(item) in (int, float) and type(value) in (int, float))) and item == value
        for item in schema["enum"]
    ):
        return False
    measured = len(value) if isinstance(value, str) else value
    for key, lower in (("minimum", True), ("maximum", False), ("minLength", True), ("maxLength", False)):
        if key in schema and (measured < schema[key] if lower else measured > schema[key]):
            return False
    return True


def _read_tool(entry: dict[str, Any], provider: str) -> tuple[dict[str, Any] | None, str]:
    tools = entry.get("tools")
    if not isinstance(tools, list) or len(tools) > MAX_TOOLS or any(not isinstance(tool, dict) for tool in tools):
        return None, "invalid_tool_inventory"
    names = [tool.get("name") for tool in tools]
    if any(not isinstance(name, str) for name in names) or len(names) != len(set(names)):
        return None, "ambiguous_tool_inventory"
    definition = REGISTRY[provider]
    tool = next((tool for tool in tools if tool["name"] == definition["tool"]), None)
    if tool is None:
        return None, "initial_read_tool_missing"
    hints = tool.get("annotations", {})
    if (not isinstance(hints, dict)
            or any(key in hints and type(hints[key]) is not bool for key in ("destructiveHint", "readOnlyHint"))
            or hints.get("destructiveHint") is True or hints.get("readOnlyHint") is False):
        return None, "conflicting_tool_annotations"
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict) or set(schema) - SCHEMA_METADATA - {"type", "properties", "required", "additionalProperties"}:
        return None, "unsupported_input_schema"
    properties, required = schema.get("properties"), schema.get("required", [])
    if schema.get("type") != "object" or not isinstance(properties, dict) or not isinstance(required, list):
        return None, "unsupported_input_schema"
    if "additionalProperties" in schema and type(schema["additionalProperties"]) is not bool:
        return None, "unsupported_input_schema"
    if any(not isinstance(key, str) for key in required):
        return None, "unsupported_input_schema"
    field = definition["query_field"]
    supported = {field, *definition["limits"]}
    if set(required) - supported or any(key not in properties for key in required):
        return None, "unsupported_required_arguments"
    query_schema = properties.get(field)
    if not _scalar_shape(query_schema) or query_schema.get("type") != "string":
        return None, "unsupported_query_schema"
    for key in set(required) - {field}:
        if not _accepts(definition["limits"][key], properties[key]):
            return None, "unsupported_required_arguments"
    return tool, "advertised_read_tool"


def _matches_root(value: Any, root: Path) -> bool:
    try:
        return isinstance(value, str) and Path(value).is_absolute() and Path(value).resolve() == root.resolve()
    except (OSError, ValueError, RuntimeError):
        return False


def discovery(metadata: dict[str, Any], project: Path, vault: Path, inventory: dict[str, Any], inventory_error: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"schema_version": PROVIDER_RUNTIME_VERSION, "query_executed": False, "providers": {}}
    try:
        selections = resolve_provider_settings({}, metadata)["providers"]
    except ValueError as error:
        result["configuration_error"] = str(error)
        selections = dict.fromkeys(PROVIDER_SLOTS)
    connections = Counter(entry.get("connection_id") for entry in inventory.values()
                          if isinstance(entry, dict) and isinstance(entry.get("connection_id"), str))
    for slot, provider in selections.items():
        status = {"provider": provider, "availability": "disabled", "reason": "not_selected", "freshness": "unknown"}
        result["providers"][slot] = status
        if provider is None:
            continue
        if provider not in REGISTRY:
            status.update(availability="unsupported", reason="provider_not_supported")
            continue
        if inventory_error:
            status.update(availability="unavailable", reason=inventory_error)
            continue
        entry = inventory.get(provider)
        if not isinstance(entry, dict):
            status.update(availability="not_discovered", reason="no_host_inventory")
            continue
        connection = entry.get("connection_id")
        if (not isinstance(connection, str) or not connection.strip() or len(connection) > 160
                or connections[connection] != 1 or entry.get("scope_binding") != "server_default"):
            status.update(availability="scope_mismatch", reason="unverified_or_ambiguous_connection")
            continue
        if entry.get("error") is not None:
            status.update(availability="unavailable", reason="host_reported_error")
            continue
        if (not _matches_root(entry.get("project_root"), project)
                or (provider == "graphify" and not _matches_root(entry.get("vault_root"), vault))):
            status.update(availability="scope_mismatch", reason="wrong_default_corpus")
            continue
        if not project.is_dir():
            status.update(availability="unavailable", reason="project_root_missing")
            continue
        tool, reason = _read_tool(entry, provider)
        status.update(availability="available" if tool else "incompatible", reason=reason)
        if tool:
            status.update(connection_id=connection, scope_binding="server_default", tool=tool["name"])
    return result


def reference_context(project: Path, raw: str) -> dict[str, Any]:
    # The trace grammar is unchanged; extra boundary checks apply to query context.
    ref = parse_code_ref(raw)
    path = str(ref["path"])
    if PureWindowsPath(path).drive or ":" in path or "\x00" in path:
        raise ValueError("live reference must be a safe project-relative path")
    target = (project / path).resolve()
    if not target.is_relative_to(project.resolve()):
        raise ValueError("live reference escapes project root")
    return {**ref, "uri": target.as_uri(), "exists": target.is_file(), "symbol_resolution": "unverified"}


def route(intent: str, query: str, metadata: dict[str, Any], project: Path, vault: Path,
          inventory: dict[str, Any], *, inventory_error: str | None = None, live_ref: str | None = None) -> dict[str, Any]:
    intent = intent.upper()
    if intent not in INTENTS or not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_LENGTH:
        raise ValueError("route needs WHAT/HOW/WHY and a query of 1..4096 characters")
    report = discovery(metadata, project, vault, inventory, inventory_error)
    slot = INTENTS[intent]
    state = report["providers"].get(slot, {})
    result = {**report, "intent": intent, "preferred_provider": state.get("provider") if slot else "wiki",
              "selected": "local" if intent == "HOW" else "wiki", "degraded": slot is not None,
              "fallback": FALLBACKS[intent], "call": None}
    if live_ref:
        result["reference"] = reference_context(project, live_ref)
        if not result["reference"]["exists"]:
            result["reason"] = "live_path_missing"
            return result
    if not slot or state.get("availability") != "available":
        result["reason"] = state.get("reason", "canonical_wiki")
        return result
    provider = state["provider"]
    tool, _ = _read_tool(inventory[provider], provider)
    assert tool is not None  # Discovery accepted this same immutable inventory.
    definition = REGISTRY[provider]
    properties = tool["inputSchema"]["properties"]
    field = definition["query_field"]
    if not _accepts(query, properties[field]):
        result["reason"] = "query_does_not_match_schema"
        return result
    arguments = {field: query}
    arguments.update({key: value for key, value in definition["limits"].items()
                      if key in properties and _accepts(value, properties[key])})
    result.update(selected=provider, degraded=False, reason="host_read_required", call={
        "connection_id": state["connection_id"], "scope_binding": "server_default",
        "tool": tool["name"], "arguments": arguments,
        "project_root": str(project.resolve()), "vault_root": str(vault.resolve()),
        "before_call": "Reconfirm this exact trusted connection, tool schema and server-default corpus; fall back if changed or unverified.",
        "after_call": "Check returned paths and claims against current sources; freshness remains unknown. Never accept a trace baseline from graph output.",
    })
    return result


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault-root", type=Path, default=Path.cwd())
    parser.add_argument("--project-root", type=Path, help="Explicit live root, as in game_trace; defaults to manifest.")
    parser.add_argument("--inventory", type=Path, help="Ephemeral tools/list data from a trusted, scoped host connection.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    routing = commands.add_parser("route")
    routing.add_argument("intent", type=str.upper, choices=tuple(INTENTS))
    routing.add_argument("--query", required=True)
    routing.add_argument("--live-ref")
    args = parser.parse_args()
    try:
        vault = args.vault_root.resolve()
        manifest = json.loads((vault / ".llm-wiki.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("project_mode") != "game" or not isinstance(manifest.get("game_project"), dict):
            raise ValueError("expected a Game vault manifest")
        project = args.project_root or project_root_from_manifest(vault)
        if project is None:
            raise ValueError("project root is missing from manifest; pass --project-root")
        project = project.resolve()
        inventory, error = read_inventory(args.inventory)
        metadata = manifest["game_project"]
        result = (discovery(metadata, project, vault, inventory, error) if args.command == "status" else
                  route(args.intent, args.query, metadata, project, vault, inventory, inventory_error=error, live_ref=args.live_ref))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, RecursionError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
