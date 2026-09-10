import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/harness/advice"))
sys.path.insert(0, str(ROOT / "tools/harness/feedback"))
spec = importlib.util.spec_from_file_location("harness_setup", ROOT / "tools/harness/setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
import bundle
import gemini
import key
import session
from local_files import require_untracked_runtime, private_dir


class InstallTests(unittest.TestCase):
    def test_new_install_and_repeat_preserve_existing_product(self):
        with tempfile.TemporaryDirectory(prefix="astra-install-") as folder:
            target = Path(folder)
            first = setup.install(ROOT, target, True)
            self.assertFalse(first["needsAgentMerge"])
            self.assertNotIn("Astra向け開発運用一式の保守", (target / "PROJECT.md").read_text(encoding="utf-8"))
            self.assertFalse((target / "docs/harness/tasks/done").exists())
            self.assertFalse((target / ".local").exists())
            checked = subprocess.run(["node", str(target / "tools/harness/check.mjs")], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertTrue(all(x["status"] == "same" for x in setup.install(ROOT, target)["files"]))
            (target / "PROJECT.md").write_text("Product settings", encoding="utf-8")
            (target / "AGENTS.md").write_text("Product contracts", encoding="utf-8")
            (target / "package.json").write_text('{"name":"product","type":"commonjs"}', encoding="utf-8")
            (target / "docs/harness/NEXT_TASKS.md").write_text("Existing tasks", encoding="utf-8")
            result = setup.install(ROOT, target, True)
            self.assertEqual(result["needsAgentMerge"], ["AGENTS.md"])
            self.assertEqual((target / "AGENTS.md").read_text(), "Product contracts")
            self.assertEqual((target / "PROJECT.md").read_text(), "Product settings")
            self.assertEqual((target / "docs/harness/NEXT_TASKS.md").read_text(), "Existing tasks")
            self.assertEqual(json.loads((target / "package.json").read_text())["name"], "product")
            self.assertEqual((target / ".gitignore").read_text().count(".local/"), 1)
            modules = subprocess.run(["node", "--test", str(target / "tests/feedback/client.test.mjs")], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(modules.returncode, 0, modules.stdout + modules.stderr)

    def test_symlink_escape_rejected_before_any_install_write(self):
        with tempfile.TemporaryDirectory(prefix="astra-safe-") as folder:
            parent = Path(folder)
            target = parent / "target"
            outside = parent / "outside"
            target.mkdir()
            outside.mkdir()
            try:
                (target / "docs").symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("directory symlinks unavailable")
            with self.assertRaises(ValueError):
                setup.install(ROOT, target, True)
            self.assertFalse((target / "AGENTS.md").exists())
            self.assertEqual(list(outside.iterdir()), [])

    def test_existing_ignore_negation_cannot_expose_runtime_and_product_license_is_preserved(self):
        with tempfile.TemporaryDirectory(prefix="astra-ignore-") as folder:
            root = Path(folder)
            bundle.git(root, "init", "-b", "test")
            (root / ".gitignore").write_text(".local/\n!.local/\n", encoding="utf-8")
            (root / "LICENSE").write_text("Product license", encoding="utf-8")
            setup.install(ROOT, root, True)
            ignored = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", "--", ".local/answers.json"], capture_output=True)
            self.assertEqual(ignored.returncode, 0)
            require_untracked_runtime(private_dir(root / ".local/feedback/test"))
            with self.assertRaises(ValueError):
                require_untracked_runtime(private_dir(root / "public/feedback"))
            (root / ".local/tracked.json").write_text("{}")
            bundle.git(root, "add", "-f", ".local/tracked.json")
            with self.assertRaises(ValueError):
                require_untracked_runtime(root / ".local")
            self.assertEqual((root / "LICENSE").read_text(), "Product license")
            self.assertIn("MIT License", (root / "docs/harness/LICENSE").read_text())
            self.assertIn("MIT License", setup.assets(root)["docs/harness/LICENSE"].decode())
            # Verify a Python consumer from the installed tree, not just its document links.
            result = subprocess.run([sys.executable, str(root / "tools/harness/advice/gemini.py"), "--help"], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_runtime_ignore_must_exclude_directory_not_one_example_file(self):
        with tempfile.TemporaryDirectory(prefix="astra-ignore-") as folder:
            root = Path(folder)
            bundle.git(root, "init", "-b", "test")
            runtime = private_dir(root / "feedback")
            ignore = root / ".gitignore"
            ignore.write_text("feedback/*\n!feedback/session.json\n!feedback/submissions/\n")
            with self.assertRaises(ValueError):
                require_untracked_runtime(runtime)
            ignore.write_text("feedback/\n!feedback/session.json\n")
            require_untracked_runtime(runtime)

    def test_doctor_does_not_print_secret_or_claim_live_connection(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"GEMINI_API_KEY": "private-marker", "CODEX_THREAD_ID": "private-id", "CODEX_APP_TOOLS_PIPE_PATH": "private-pipe"}):
            report = setup.doctor(Path(folder))
            self.assertNotIn("private-", json.dumps(report))
            self.assertEqual(report["gemini"]["state"], "configured-unverified")
            self.assertEqual(report["desktop"]["state"], "configured-unverified")


class AdviceTests(unittest.TestCase):
    def fixture(self, path):
        def git(*args):
            return bundle.git(path, *args)
        git("init", "-b", "test")
        git("config", "user.name", "Test")
        git("config", "user.email", "test@example.test")
        git("config", "commit.gpgsign", "false")
        git("config", "core.autocrlf", "false")
        (path / ".gitignore").write_text(".local/\nignored.md\n", encoding="utf-8")
        (path / "one.py").write_text("original = True\n", encoding="utf-8")
        git("add", ".gitignore", "one.py")
        git("commit", "-m", "base")
        return git, bundle.ref(path, "HEAD")

    def test_bundle_snapshot_scope_and_uncommitted_opt_in(self):
        with tempfile.TemporaryDirectory(prefix="astra-bundle-") as folder:
            root = Path(folder)
            git, base = self.fixture(root)
            (root / "one.py").write_text("committed = True\n", encoding="utf-8")
            git("add", "one.py")
            git("commit", "-m", "change")
            (root / "one.py").write_text("working_only = True\n", encoding="utf-8")
            committed = bundle.make_bundle(root, base, "HEAD", ["one.py"], "Review behavior")
            self.assertIn("committed = True", committed)
            self.assertNotIn("working_only", committed)
            live = bundle.make_bundle(root, base, "HEAD", ["one.py"], "Review behavior", True)
            self.assertIn("working_only = True", live)
            self.assertNotIn("test@example.test", committed)
            self.assertNotIn(str(root), committed)
            (root / "untracked.py").write_text("private")
            with self.assertRaises(ValueError):
                bundle.make_bundle(root, base, "HEAD", ["untracked.py"], "Review")
            git("add", "untracked.py")
            self.assertIn("private", bundle.make_bundle(root, base, "HEAD", ["untracked.py"], "Review", True))

    def test_bundle_rejects_secret_in_diff_and_force_tracked_ignore(self):
        with tempfile.TemporaryDirectory(prefix="astra-bundle-") as folder:
            root = Path(folder)
            git, base = self.fixture(root)
            (root / "ignored.md").write_text("private", encoding="utf-8")
            git("add", "-f", "ignored.md")
            git("commit", "-m", "force tracked")
            with self.assertRaises(ValueError):
                bundle.make_bundle(root, base, "HEAD", ["ignored.md"], "Review")
            (root / "one.py").write_text("value = '" + "gh" + "p_" + "X" * 30 + "'\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                bundle.make_bundle(root, base, "HEAD", ["one.py"], "Review", True)
            for name in ("../one.py", ".env", "secrets.json"):
                with self.assertRaises(ValueError):
                    bundle.make_bundle(root, base, "HEAD", [name], "Review")

    def test_historical_path_does_not_admit_untracked_replacement(self):
        with tempfile.TemporaryDirectory(prefix="astra-bundle-") as folder:
            root = Path(folder)
            git, base = self.fixture(root)
            git("rm", "one.py")
            git("commit", "-m", "remove")
            self.assertIn("(deleted)", bundle.make_bundle(root, base, "HEAD", ["one.py"], "Review", True))
            (root / "one.py").write_text("UNTRACKED_PRIVATE_CONTENT", encoding="utf-8")
            with self.assertRaises(ValueError) as caught:
                bundle.make_bundle(root, base, "HEAD", ["one.py"], "Review", True)
            self.assertNotIn("UNTRACKED_PRIVATE_CONTENT", str(caught.exception))

    def test_gemini_dry_run_no_network_and_visual_requires_image(self):
        with tempfile.TemporaryDirectory(prefix="astra-gemini-") as folder:
            prompt = Path(folder) / "question.md"
            prompt.write_text("PRIVATE_QUESTION", encoding="utf-8")
            with patch.object(sys, "argv", ["gemini.py", "--prompt-file", str(prompt), "--role", "creative"]), patch.object(gemini, "urlopen") as send, patch("builtins.print") as output:
                gemini.main()
            send.assert_not_called()
            summary = json.loads(output.call_args.args[0])
            self.assertFalse(summary["sent"])
            self.assertNotIn("PRIVATE_QUESTION", output.call_args.args[0])
            with self.assertRaises(ValueError):
                gemini.payload("Review", [], gemini.DEFAULT_MODEL, "visual", "high")
            self.assertFalse(gemini.payload("Review", [], gemini.DEFAULT_MODEL, "creative", "high")["store"])

    def test_gemini_timeout_does_not_retry_or_echo_key(self):
        with tempfile.TemporaryDirectory(prefix="astra-gemini-") as folder:
            prompt = Path(folder) / "question.md"
            prompt.write_text("Review", encoding="utf-8")
            with patch.object(sys, "argv", ["gemini.py", "--prompt-file", str(prompt), "--role", "creative", "--send"]), patch.dict(os.environ, {"GEMINI_API_KEY": "private-key-marker"}), patch.object(gemini, "urlopen", side_effect=TimeoutError("private-key-marker")) as send:
                with self.assertRaises(ValueError) as caught:
                    gemini.main()
            self.assertEqual(send.call_count, 1)
            self.assertNotIn("private-key-marker", str(caught.exception))

    def test_connection_probe_has_no_prompt_and_redirects_never_forward_keys(self):
        with patch.object(sys, "argv", ["gemini.py", "--check-connection"]), patch.dict(os.environ, {"GEMINI_API_KEY": "private-key-marker"}), patch.object(gemini, "request_json", return_value={"name": "models/" + gemini.DEFAULT_MODEL}) as send, patch("builtins.print") as output:
            gemini.main()
        request = send.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)
        self.assertNotIn("private-key-marker", request.full_url)
        self.assertFalse(json.loads(output.call_args.args[0])["generationVerified"])
        with self.assertRaises(ValueError):
            gemini.NoRedirect().redirect_request(request, None, 302, "Found", {}, "https://elsewhere.invalid/")
        self.assertEqual(gemini.payload("Review", [], gemini.DEFAULT_MODEL, "creative", "high")["generation_config"]["max_output_tokens"], 4096)
        with self.assertRaises(ValueError):
            gemini.payload("Review", [], gemini.DEFAULT_MODEL, "creative", "high", 0)

    def test_malformed_environment_key_and_http_errors_never_echo_secret(self):
        marker = "private-test-key"
        for value in (marker + "\n", marker + "\r", marker + "\t", marker + "日本語"):
            result = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "tools/harness/advice/gemini.py"), "--check-connection"],
                                    env={**os.environ, "GEMINI_API_KEY": value},
                                    capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 1)
            self.assertNotIn(marker, result.stdout + result.stderr)
            self.assertIn("形式", result.stderr)
        with patch.object(gemini, "urlopen", side_effect=ValueError(marker)):
            with self.assertRaises(ValueError) as caught:
                gemini.request_json(gemini.Request(gemini.ENDPOINT))
            self.assertNotIn(marker, str(caught.exception))

    @unittest.skipUnless(os.name == "nt", "Windows junction boundary")
    def test_working_tree_bundle_rejects_junction_before_reading_outside(self):
        with tempfile.TemporaryDirectory(prefix="astra-junction-") as folder:
            parent = Path(folder)
            root, outside = parent / "repo", parent / "outside"
            root.mkdir()
            outside.mkdir()
            git, base = self.fixture(root)
            (root / "src").mkdir()
            (root / "src/item.py").write_text("public = True")
            git("add", "src/item.py")
            git("commit", "-m", "add source")
            (root / "src/item.py").unlink()
            (root / "src").rmdir()
            (outside / "item.py").write_text("PRIVATE_OUTSIDE_DATA")
            subprocess.run(["powershell", "-NoProfile", "-Command", "New-Item -ItemType Junction -Path $env:HARNESS_LINK -Target $env:HARNESS_OUTSIDE | Out-Null"],
                           env={**os.environ, "HARNESS_LINK": str(root / "src"), "HARNESS_OUTSIDE": str(outside)}, check=True, capture_output=True)
            try:
                with self.assertRaises(ValueError) as caught:
                    bundle.make_bundle(root, base, "HEAD", ["src/item.py"], "Review", True)
                self.assertNotIn("PRIVATE_OUTSIDE_DATA", str(caught.exception))
            finally:
                (root / "src").rmdir()

    def test_key_roundtrip_local_only_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="astra-key-") as folder, patch.dict(os.environ, {}, clear=True):
            root = Path(folder)
            marker = "fake-test-credential"
            key.save_key(root, marker)
            self.assertEqual(key.load_key(root), marker)
            with self.assertRaises(FileExistsError):
                key.save_key(root, "second-value")
            if os.name == "nt":
                self.assertNotIn(marker.encode(), key.key_path(root).read_bytes())
            else:
                self.assertEqual(key.key_path(root).stat().st_mode & 0o777, 0o600)


class TaskListTests(unittest.TestCase):
    def test_empty_choice_and_malformed_registry(self):
        with tempfile.TemporaryDirectory(prefix="astra-tasks-") as folder:
            root = Path(folder)
            index = root / "NEXT_TASKS.md"
            index.write_text("# Tasks\n", encoding="utf-8")
            self.assertEqual(session.task_config(index, "keep-key")["mode"], "explain")
            (root / "tasks").mkdir()
            (root / "tasks/one.md").write_text("Spec", encoding="utf-8")
            index.write_text("- [One](tasks/one.md) — Summary\n", encoding="utf-8")
            result = session.task_config(index, "keep-key")
            self.assertEqual(result["mode"], "choose")
            self.assertEqual(result["decisions"], ["One", "今回は選ばない"])
            self.assertEqual(result["storageKey"], "keep-key")
            self.assertEqual(session.task_config(index, "keep-key", True)["mode"], "explain")
            index.write_text("- Summary → [One](tasks/one.md)\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                session.task_config(index, "keep-key")


if __name__ == "__main__":
    unittest.main()
