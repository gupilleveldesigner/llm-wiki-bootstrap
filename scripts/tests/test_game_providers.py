from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "assets/project-modes/game/runtime"))
import game_providers as providers  # noqa: E402
from game_provider_config import resolve_provider_settings  # noqa: E402
from game_project_install import install_game_router  # noqa: E402
from game_project_contract import GAME_ROUTER_MARKER, GAME_PROVIDER_ROUTER_MARKER  # noqa: E402


class ProviderConfigTests(unittest.TestCase):
    def test_legacy_defaults_partial_overrides_and_explicit_disable(self):
        self.assertEqual(resolve_provider_settings({})["providers"], {"code_intelligence": None, "knowledge_graph": None})
        previous = resolve_provider_settings({"providers": {"code_intelligence": "codegraph", "knowledge_graph": "graphify"}})
        before = copy.deepcopy(previous)
        self.assertEqual(resolve_provider_settings({}, previous), previous)
        self.assertEqual(resolve_provider_settings({"providers": {}}, previous), previous)
        updated = resolve_provider_settings({"providers": {"knowledge_graph": None}}, previous)
        self.assertEqual(updated["providers"], {"code_intelligence": "codegraph", "knowledge_graph": None})
        self.assertEqual(previous, before)

    def test_future_provider_ids_are_preserved_without_loading_them(self):
        self.assertEqual(resolve_provider_settings({"providers": {"code_intelligence": "future_provider"}})["providers"]["code_intelligence"], "future_provider")

    def test_invalid_config_and_future_schema_fail(self):
        for invalid in (None, [], "codegraph", {"typo": "graphify"}, {"code_intelligence": 1},
                        {"code_intelligence": "graphify"}, {"knowledge_graph": "codegraph"},
                        {"knowledge_graph": {"command": "execute"}}, {"knowledge_graph": "../plugin"}):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                resolve_provider_settings({"providers": invalid})
        for version in (True, "1", 2, None):
            with self.subTest(version=version), self.assertRaises(ValueError):
                resolve_provider_settings({}, {"provider_schema_version": version})

    def test_v5_router_gets_non_destructive_provider_proposals(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("CLAUDE.md", "AGENTS.md", "wiki/CLAUDE.md"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("User instructions\n" + GAME_ROUTER_MARKER, encoding="utf-8")
            proposals = install_game_router(root, propose_existing=True)
            self.assertEqual(len(proposals), 3)
            install_game_router(root, propose_existing=True)
            for name in proposals:
                text = (root / name).read_text(encoding="utf-8")
                self.assertEqual(text.count(GAME_PROVIDER_ROUTER_MARKER), 1)
                self.assertIn("User instructions", text)
                original = root / name.removesuffix(".wiki-proposed")
                self.assertNotIn(GAME_PROVIDER_ROUTER_MARKER, original.read_text(encoding="utf-8"))


class ProviderRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.project, self.vault = root / "Game", root / "Game.wiki"
        self.project.mkdir()
        self.vault.mkdir()
        (self.project / "player.py").write_text("def jump():\n    return 1\n", encoding="utf-8")
        self.metadata = resolve_provider_settings({"providers": {"code_intelligence": "codegraph", "knowledge_graph": "graphify"}})
        self.inventory = {
            "codegraph": {
                "connection_id": "codegraph-game", "scope_binding": "server_default",
                "project_root": str(self.project),
                "tools": [{"name": "codegraph_symbol_search", "inputSchema": {
                    "type": "object", "properties": {"query": {"type": "string"},
                    # Pinned CodeGraph tools.rs uses number_prop (default 20.0).
                    "limit": {"type": "number", "default": 20.0}, "compact": {"type": "boolean"}}, "required": ["query"]}}],
            },
            "graphify": {
                "connection_id": "graphify-game", "scope_binding": "server_default",
                "project_root": str(self.project), "vault_root": str(self.vault),
                "tools": [{"name": "query_graph", "inputSchema": {
                    "type": "object", "properties": {"question": {"type": "string"},
                    "project_path": {"type": "string"}, "token_budget": {"type": "integer"}}, "required": ["question"]}}],
            },
        }

    def route(self, intent, inventory=None, **kwargs):
        return providers.route(intent, "jump", self.metadata, self.project, self.vault,
                               self.inventory if inventory is None else inventory, **kwargs)

    def test_two_providers_route_independently_and_why_remains_wiki(self):
        for intent, selected, tool in (("WHAT", "graphify", "query_graph"), ("HOW", "codegraph", "codegraph_symbol_search")):
            with self.subTest(intent=intent):
                result = self.route(intent)
                self.assertEqual(result["selected"], selected)
                self.assertEqual(result["call"]["tool"], tool)
                self.assertEqual(result["call"]["connection_id"], selected + "-game")
                self.assertFalse(result["query_executed"])
                self.assertFalse(result["degraded"])
                self.assertNotIn("project_path", result["call"]["arguments"])
                self.assertTrue(all(item["freshness"] == "unknown" for item in result["providers"].values()))
        result = self.route("WHY")
        self.assertEqual(result["selected"], "wiki")
        self.assertIsNone(result["call"])
        self.assertFalse(result["degraded"])

    def test_absent_one_or_both_providers_falls_back_without_execution_or_writes(self):
        before = (self.project / "player.py").read_bytes()
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("provider process executed")):
            self.assertEqual(self.route("WHAT", {})["selected"], "wiki")
            self.assertEqual(self.route("HOW", {})["selected"], "local")
            del self.inventory["codegraph"]
            self.assertEqual(self.route("WHAT")["selected"], "graphify")
            self.assertEqual(self.route("HOW")["providers"]["code_intelligence"]["availability"], "not_discovered")
        self.assertEqual(before, (self.project / "player.py").read_bytes())
        self.assertEqual(list(self.vault.iterdir()), [])

    def test_disabled_unknown_and_future_config_do_not_enable_tools(self):
        self.metadata = resolve_provider_settings({})
        self.assertEqual(self.route("HOW")["providers"]["code_intelligence"]["availability"], "disabled")
        self.metadata["providers"]["code_intelligence"] = "future_provider"
        self.assertEqual(self.route("HOW")["providers"]["code_intelligence"]["availability"], "unsupported")
        self.metadata["provider_schema_version"] = 2
        result = self.route("HOW")
        self.assertIn("configuration_error", result)
        self.assertIsNone(result["call"])

    def test_wrong_unverified_or_changed_default_binding_produces_no_call(self):
        for change in ({"project_root": str(self.vault)}, {"vault_root": str(self.project)},
                       {"scope_binding": "unverified"}, {"scope_binding": "project_path"},
                       {"connection_id": ""}, {"connection_id": "codegraph-game"}):
            with self.subTest(change=change):
                inventory = copy.deepcopy(self.inventory)
                inventory["graphify"].update(change)
                result = self.route("WHAT", inventory)
                self.assertEqual(result["providers"]["knowledge_graph"]["availability"], "scope_mismatch")
                self.assertIsNone(result["call"])
        del self.inventory["graphify"]["scope_binding"]
        self.assertIsNone(self.route("WHAT")["call"])

    def test_identical_display_names_use_exact_unique_connection_ids(self):
        # A host must supply internal IDs. Display names never select a tool.
        for entry in self.inventory.values():
            entry["display_name"] = "same name"
        self.assertEqual(self.route("WHAT")["call"]["connection_id"], "graphify-game")
        self.assertEqual(self.route("HOW")["call"]["connection_id"], "codegraph-game")

    def test_host_errors_degrade_without_leaking_response_text(self):
        self.inventory["graphify"]["error"] = "timeout: private upstream response"
        result = self.route("WHAT")
        self.assertIsNone(result["call"])
        self.assertEqual(result["providers"]["knowledge_graph"]["availability"], "unavailable")
        self.assertNotIn("private upstream response", json.dumps(result))

    def test_tool_renames_duplicates_annotations_and_schema_drift_degrade(self):
        original = self.inventory["codegraph"]["tools"][0]
        variants = []
        for mutation in (
            {"name": "renamed_search"}, {"annotations": {"destructiveHint": True}},
            {"annotations": {"destructiveHint": "false"}},
            {"annotations": {"readOnlyHint": False}},
            {"inputSchema": {"type": "array"}},
            {"inputSchema": {"type": "object", "properties": {"query": {"$ref": "remote"}}}},
            {"inputSchema": {**original["inputSchema"], "oneOf": []}},
            {"inputSchema": {**original["inputSchema"], "required": ["query", "workspace"]}},
        ):
            variants.append([{**original, **mutation}])
        variants.extend(([original, original], [original] * (providers.MAX_TOOLS + 1)))
        for tools in variants:
            with self.subTest(tools=tools[:1]):
                inventory = copy.deepcopy(self.inventory)
                inventory["codegraph"]["tools"] = tools
                result = self.route("HOW", inventory)
                self.assertIsNone(result["call"])
                self.assertEqual(result["providers"]["code_intelligence"]["availability"], "incompatible")
        self.inventory["graphify"]["tools"][0]["inputSchema"]["required"].append("project_path")
        self.assertIsNone(self.route("WHAT")["call"])

    def test_query_constraints_and_required_limits_are_checked(self):
        schema = self.inventory["codegraph"]["tools"][0]["inputSchema"]
        self.assertEqual(self.route("HOW")["call"]["arguments"]["limit"], 8)
        schema["properties"]["limit"].update(minimum=1.0, maximum=8.0, enum=[8.0])
        self.assertEqual(self.route("HOW")["call"]["arguments"]["limit"], 8)
        del schema["properties"]["limit"]["enum"]
        schema["properties"]["limit"]["maximum"] = float("inf")
        self.assertNotIn("limit", self.route("HOW")["call"]["arguments"])
        del schema["properties"]["limit"]["maximum"]
        schema["properties"]["query"]["maxLength"] = 2
        self.assertIsNone(self.route("HOW")["call"])
        del schema["properties"]["query"]["maxLength"]
        schema["properties"]["limit"]["minimum"] = 50
        self.assertNotIn("limit", self.route("HOW")["call"]["arguments"])
        schema["required"].append("limit")
        self.assertIsNone(self.route("HOW")["call"])
        for query in ("", " " * 2, "x" * (providers.MAX_QUERY_LENGTH + 1)):
            with self.subTest(query=query[:10]), self.assertRaises(ValueError):
                providers.route("HOW", query, self.metadata, self.project, self.vault, {})

    def test_symbol_context_is_advisory_and_existing_fingerprints_stay_file_scoped(self):
        from game_trace import code_fingerprint
        before = code_fingerprint(self.project, "player.py#jump")
        result = self.route("HOW", live_ref="player.py#jump@L1-2")
        self.assertEqual(result["reference"]["symbol"], "jump")
        self.assertEqual(result["reference"]["locator"], "L1-2")
        self.assertEqual(result["reference"]["symbol_resolution"], "unverified")
        self.assertEqual(result["reference"]["uri"], (self.project / "player.py").as_uri())
        self.assertEqual(before["scope"], "file")
        self.assertEqual(before, code_fingerprint(self.project, "player.py#jump"))
        self.assertTrue(self.route("HOW", live_ref="player.py")["reference"]["exists"])
        self.assertIsNone(self.route("HOW", live_ref="missing.py#jump")["call"])

    def test_unsafe_paths_and_symlink_escape_are_rejected(self):
        for ref in ("../outside", "/outside", "C:/outside", "C:outside", "player.py:stream", "src/../outside", "\\\\server\\file"):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                self.route("HOW", live_ref=ref)
        outside = self.vault / "private.py"
        outside.write_text("private", encoding="utf-8")
        try:
            (self.project / "link.py").symlink_to(outside)
        except OSError:
            self.skipTest("symlink creation is unavailable on this host")
        with self.assertRaises(ValueError):
            self.route("HOW", live_ref="link.py#private")

    def test_inventory_limits_duplicate_keys_and_malformed_input_degrade(self):
        path = self.vault / "session.json"
        documents = ["{", "[]", '{"schema_version":2,"providers":{}}',
                     '{"schema_version":true,"providers":{}}',
                     '{"schema_version":1,"providers":{"codegraph":{},"codegraph":{}}}',
                     "x" * (providers.MAX_INVENTORY_BYTES + 1), "[" * 1200 + "]" * 1200]
        for content in documents:
            with self.subTest(size=len(content)):
                path.write_text(content, encoding="utf-8")
                inventory, error = providers.read_inventory(path)
                self.assertIsNotNone(error)
                self.assertIsNone(self.route("HOW", inventory, inventory_error=error)["call"])
        path.write_text(json.dumps({"schema_version": 1, "providers": self.inventory}), encoding="utf-8")
        inventory, error = providers.read_inventory(path)
        self.assertIsNone(error)
        self.assertEqual(self.route("WHAT", inventory)["selected"], "graphify")


if __name__ == "__main__":
    unittest.main()
