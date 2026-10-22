"""Preservation and repeat-application checks for the portable installer."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("recipe_install", ROOT / "install.py")
INSTALL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALL)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex-recipe-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob("*") if p.is_file() and ".git" not in p.parts}

    def test_pure_plan_matches_installer_bytes_and_return_contract(self):
        (self.root / ".gitignore").write_bytes(b"custom/\r\n")
        before = self.snapshot()
        writes = INSTALL.plan_install(self.root)
        self.assertEqual(before, self.snapshot())
        self.assertTrue(all(isinstance(value, bytes) for value in writes.values()))
        self.assertEqual(INSTALL.install(self.root, check=True), sorted(writes))
        self.assertEqual(before, self.snapshot())
        self.assertEqual(INSTALL.install(self.root), sorted(writes))
        for name, payload in writes.items():
            self.assertEqual((self.root / name).read_bytes(), payload)
        self.assertEqual(INSTALL.plan_install(self.root), {})

    def test_plan_rejects_nonregular_destination_before_reading_it(self):
        path = self.root / ".gitignore"
        os.mkfifo(path)
        with self.assertRaises(ValueError):
            INSTALL.plan_install(self.root)

    def test_native_display_asset_is_inert_until_explicitly_wired(self):
        INSTALL.install(self.root)
        adapter = self.root / ".codex/hooks/native_display.py"
        self.assertEqual(adapter.read_bytes(), (ROOT / ".codex/hooks/native_display.py").read_bytes())
        self.assertEqual((self.root / ".codex/native-display.md").read_bytes(),
                         (ROOT / "native-display.md").read_bytes())
        self.assertNotIn("native_display", (self.root / ".codex/hooks.json").read_text())
        adapter.write_text("# preserved customization\n")
        before = self.snapshot()
        with self.assertRaises(ValueError):
            INSTALL.install(self.root)
        self.assertEqual(before, self.snapshot())

    def test_transient_declarations_excluded_without_losing_custom_rules(self):
        for name in (".gitignore", ".graphifyignore"):
            (self.root / name).write_text("custom-cache/\n")
        INSTALL.install(self.root)
        for name in (".gitignore", ".graphifyignore"):
            self.assertEqual((self.root / name).read_text(),
                             "custom-cache/\n.codex-delegations/\n")
        record = self.root / ".codex-delegations/reader.json"
        record.parent.mkdir()
        record.write_text("{}")
        self.assertEqual(subprocess.run(["git", "check-ignore", "-q", str(record)],
                                       cwd=self.root).returncode, 0)
        first = self.snapshot()
        self.assertEqual(INSTALL.install(self.root), [])
        self.assertEqual(first, self.snapshot())

    def test_python_and_nested_frontend_reruns_preserve_customization(self):
        for nested in ("src", "web/app"):
            with self.subTest(nested=nested):
                (self.root / nested).mkdir(parents=True, exist_ok=True)
                config = self.root / ".codex/config.toml"
                config.parent.mkdir(exist_ok=True)
                config.write_text('# User setting\nmodel_reasoning_effort = "high"\n'
                                  '[agents]\nmax_concurrent_threads_per_session = 2\n')
                hooks = self.root / ".codex/hooks.json"
                custom = {"hooks": {"SessionStart": [{"hooks": [
                    {"type": "command", "command": "printf existing"}]}]}}
                hooks.write_text(json.dumps(custom))
                original = config.read_bytes()
                self.assertTrue(INSTALL.install(self.root, check=True))
                self.assertEqual(json.loads(hooks.read_text()), custom)
                INSTALL.install(self.root)
                first = self.snapshot()
                self.assertEqual(INSTALL.install(self.root), [])
                self.assertEqual(INSTALL.install(self.root, check=True), [])
                self.assertEqual(first, self.snapshot())
                self.assertEqual(config.read_bytes(), original)
                self.assertEqual(json.loads(hooks.read_text())["hooks"]["SessionStart"],
                                 custom["hooks"]["SessionStart"])

    def test_missing_agent_settings_are_added_without_changing_preferences(self):
        config = self.root / ".codex/config.toml"
        config.parent.mkdir()
        original = 'model_reasoning_effort = "high"\n'
        config.write_text(original)
        INSTALL.install(self.root)
        self.assertTrue(config.read_text().startswith(original))
        import tomllib
        parsed = tomllib.loads(config.read_text())
        self.assertEqual(parsed["agents"]["max_concurrent_threads_per_session"], 3)
        self.assertTrue(parsed["agents"]["enabled"])
        self.assertEqual(parsed["model_reasoning_effort"], "high")

    def test_incomplete_or_disabled_agent_settings_require_review_before_writes(self):
        config = self.root / ".codex/config.toml"
        config.parent.mkdir()
        for content in ('[agents]\nenabled = true\n',
                        '[agents]\nenabled = false\nmax_threads = 3\n',
                        '[agents]\nmax_threads = 3\n',
                        '[agents]\nmax_concurrent_threads_per_session = 0\n',
                        '[agents]\nmax_concurrent_threads_per_session = -1\n',
                        '[agents]\nmax_concurrent_threads_per_session = "three"\n',
                        '[agents]\nmax_concurrent_threads_per_session = true\n'):
            config.write_text(content)
            before = self.snapshot()
            with self.assertRaises(ValueError):
                INSTALL.install(self.root)
            self.assertEqual(before, self.snapshot())

    def test_conflict_preflight_never_partially_writes(self):
        script = self.root / ".codex/hooks/subagents.py"
        script.parent.mkdir(parents=True)
        script.write_text("# User customization\n")
        before = self.snapshot()
        with self.assertRaises(ValueError):
            INSTALL.install(self.root)
        self.assertEqual(before, self.snapshot())

    def test_symlink_and_nested_target_refused(self):
        (self.root / ".codex").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            INSTALL.install(self.root)
        (self.root / ".codex").unlink()
        (self.root / "web").mkdir()
        with self.assertRaises(ValueError):
            INSTALL.install(self.root / "web")

    def test_explicit_non_git_workspace_uses_quoted_local_path(self):
        with tempfile.TemporaryDirectory(prefix="codex space '") as target:
            root = Path(target)
            with self.assertRaises(ValueError):
                INSTALL.install(root)
            INSTALL.install(root, non_git=True)
            hooks = json.loads((root / ".codex/hooks.json").read_text())
            command = hooks["hooks"]["SubagentStart"][0]["hooks"][0]["command"]
            result = subprocess.run(command, shell=True, cwd=root,
                                    input='{"hook_event_name":"SubagentStart"}',
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0)
            self.assertIn("additionalContext", json.loads(result.stdout)["hookSpecificOutput"])
            child = root / "service"
            subprocess.run(["git", "init", "-q", str(child)], check=True)
            brief = {"objective": "Read the service source.",
                     "context": "The umbrella is the harness root; service is the software root.",
                     "instructions": "Make no writes; source paths are harness-root-relative.",
                     "allowed_files": [], "mutable_resources": [], "dependencies": [],
                     "acceptance": ["Return the observed result."], "checks": ["Read only."],
                     "read_only": True, "budget": {"minutes": 1, "attempts": 1}}
            (child / ".codex-delegations").mkdir()
            (child / ".codex-delegations/reader.json").write_text(json.dumps(brief))
            payload = json.dumps({"hook_event_name": "PreToolUse", "cwd": str(child),
                                  "tool_name": "spawn_agent", "tool_input": {
                                      "task_name": "reader", "message": "opaque payload"}})
            command = hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
            denied = subprocess.run(command, shell=True, cwd=child, input=payload,
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(denied.returncode, 0)
            self.assertEqual(json.loads(denied.stdout)["hookSpecificOutput"]
                             ["permissionDecision"], "deny")
            (root / ".codex-delegations").mkdir()
            (root / ".codex-delegations/reader.json").write_text(json.dumps(brief))
            accepted = subprocess.run(command, shell=True, cwd=child, input=payload,
                                      capture_output=True, text=True, timeout=5)
            self.assertEqual(accepted.returncode, 0)
            self.assertEqual(json.loads(accepted.stdout), {})
            self.assertEqual(INSTALL.install(root, non_git=True), [])
