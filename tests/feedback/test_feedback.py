"""Contract tests for the local answer/notification boundary, without invoking Codex."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools/harness/feedback"))
from review_server import Receiver, atomic_json, document
from outbox import Outbox
from session import acknowledge, check_binding, acquire, load_session
from local_files import private_dir

THREAD = "11111111-1111-1111-1111-111111111111"
OTHER = "22222222-2222-2222-2222-222222222222"
TOKEN = "a" * 32


def config():
    return {"mode": "review", "title": "Review", "storageKey": "review",
            "decisions": ["accept", "revise", "hold"], "commentRequired": ["revise"],
            "proposals": [{"id": "p1", "title": "Title", "before": "Before", "after": "After"}]}


class PrivateStorageTests(unittest.TestCase):
    def test_private_modes_atomic_failure_and_invalid_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            root = private_dir(Path(folder) / "feedback")
            target = root / "session.json"
            atomic_json(target, {"old": True})
            with patch.object(Path, "replace", side_effect=OSError):
                with self.assertRaises(OSError):
                    atomic_json(target, {"new": True})
            self.assertEqual(json.loads(target.read_text()), {"old": True})
            self.assertEqual(list(root.glob("*.tmp")), [])
            out = private_dir(root / "submissions")
            atomic_json(out / "invalid.json", {"autoResumeRequested": True, "submissionId": "invalid", "threadId": THREAD})
            queue = Outbox(out, THREAD)
            self.assertEqual(queue.status("invalid")["state"], "unknown")
            with self.assertRaises(ValueError):
                queue.enqueue(TOKEN, root / (TOKEN + ".json"))
            if os.name != "nt":
                self.assertEqual(root.stat().st_mode & 0o777, 0o700)
                self.assertEqual(target.stat().st_mode & 0o777, 0o600)
                self.assertEqual(queue.db.stat().st_mode & 0o777, 0o600)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        atomic_json(self.root / "feedback.json", config())
        self.server = Receiver(self.root, thread_id=THREAD,
                               bridge=lambda _: {"ok": True, "threadId": THREAD, "active": True})
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.version = document(self.root)[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()
        self.temp.cleanup()

    def request(self, path, body=None, headers=None):
        actual = {"X-Feedback-Key": self.server.access_key, "Origin": self.server.origin}
        actual.update(headers or {})
        data = json.dumps(body).encode() if body is not None else None
        try:
            reply = urlopen(Request(self.server.origin + path, data=data, headers=actual), timeout=3)
        except HTTPError as error:
            reply = error
        with reply:
            return reply.status, reply.read()

    def payload(self, **change):
        return {"version": self.version, "submissionId": TOKEN,
                "answers": [{"id": "p1", "decision": "accept", "comment": ""}], "general": "", **change}

    def test_saved_submission_is_idempotent_and_never_retargets(self):
        body = self.payload(threadId=OTHER, outputPath="../../elsewhere")
        status, result = self.request("/api/submit", body)
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(result)["saved"])
        saved = json.loads((self.server.out / (TOKEN + ".json")).read_text(encoding="utf-8"))
        self.assertEqual(saved["threadId"], THREAD)
        self.assertNotIn("outputPath", saved)
        self.server.queue.update(TOKEN, "uncertain")
        self.assertEqual(self.request("/api/submit", body)[0], 200)
        self.assertEqual(self.server.queue.status(TOKEN)["state"], "uncertain")
        self.assertEqual(len(list(self.server.out.glob("*.json"))), 1)
        self.assertEqual(self.request("/api/submit", self.payload(general="changed"))[0], 409)

    def test_stale_incomplete_or_invalid_answer_never_saves(self):
        for body in [
            self.payload(version="stale"),
            self.payload(answers=[]),
            self.payload(answers=[{"id": "p1", "decision": "revise", "comment": "  "}]),
            self.payload(answers=[{"id": "other", "decision": "accept", "comment": ""}]),
        ]:
            self.assertIn(self.request("/api/submit", body)[0], (400, 409))
        self.assertEqual(list(self.server.out.glob("*.json")), [])

    def test_private_files_cross_origin_and_missing_key_are_rejected(self):
        (self.root / "private.txt").write_text("PRIVATE")
        self.assertEqual(self.request("/api/review", headers={"X-Feedback-Key": ""})[0], 403)
        self.assertEqual(self.request("/api/submit", self.payload(), {"Origin": "http://foreign.invalid"})[0], 403)
        self.assertEqual(self.request("/api/submit", self.payload(), {"Host": "foreign.invalid"})[0], 403)
        for path in ("/private.txt", "/feedback.json", "/session.json", "/../private.txt", "/test-submissions/" + TOKEN + ".json"):
            self.assertEqual(self.request(path)[0], 404)
        public = self.request("/")[1].decode()
        self.assertNotIn(self.server.access_key, public)
        self.assertNotIn("Before", public)

    def test_write_failure_retains_previous_content_and_does_not_notify(self):
        with patch("review_server.atomic_json", side_effect=OSError):
            status, result = self.request("/api/submit", self.payload())
        self.assertEqual(status, 500)
        self.assertNotIn("saved", json.loads(result))
        self.assertEqual(self.server.queue.status(TOKEN)["state"], "unknown")

    def test_config_validation_is_effective_without_assertions(self):
        invalid = config()
        invalid["proposals"][0]["id"] = "../outside"
        atomic_json(self.root / "feedback.json", invalid)
        with self.assertRaisesRegex(ValueError, "設定"):
            document(self.root)

    def test_live_configuration_change_rejects_old_version(self):
        updated = config()
        updated["proposals"][0]["after"] = "Updated"
        atomic_json(self.root / "feedback.json", updated)
        self.assertEqual(self.request("/api/submit", self.payload())[0], 409)
        self.assertNotEqual(json.loads(self.request("/api/review")[1])["version"], self.version)


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "submissions"
        self.calls = []
        self.active = False
        self.status_thread = THREAD
        self.reply = {"ok": True}

        def bridge(data):
            self.calls.append(data["action"])
            if data["action"] == "status":
                return {"ok": True, "active": self.active, "threadId": self.status_thread}
            return self.reply

        self.box = Outbox(self.root, THREAD, bridge)

    def tearDown(self):
        self.temp.cleanup()

    def enqueue(self):
        path = self.root / (TOKEN + ".json")
        atomic_json(path, {"submissionId": TOKEN, "autoResumeRequested": True, "threadId": THREAD})
        self.box.enqueue(TOKEN, path)

    def test_idle_no_work_and_active_task_never_invoke_model(self):
        self.assertFalse(self.box.step())
        self.assertEqual(self.calls, [])
        self.enqueue()
        self.active = True
        self.box.step()
        self.assertEqual(self.calls, ["status"])
        self.active = False
        self.box.step()
        self.assertEqual(self.calls.count("notify"), 1)
        self.box.step()
        self.assertEqual(self.calls.count("notify"), 1)
        self.assertEqual(self.box.status(TOKEN)["state"], "notified")

    def test_wrong_task_and_unknown_status_fail_closed(self):
        self.enqueue()
        self.status_thread = OTHER
        self.box.step()
        self.assertEqual(self.box.status(TOKEN)["state"], "pending")
        self.assertNotIn("notify", self.calls)
        with self.assertRaises(ValueError):
            Outbox(self.root, OTHER)

    def test_uncertain_delivery_is_never_automatically_resent(self):
        self.enqueue()
        self.reply = {"ok": False, "uncertain": True}
        self.box.step()
        self.assertEqual(self.box.status(TOKEN)["state"], "uncertain")
        self.box.step()
        restarted = Outbox(self.root, THREAD, self.box.bridge)
        restarted.step()
        self.assertEqual(self.calls.count("notify"), 1)
        self.assertFalse(restarted.retry_failed(TOKEN))

    def test_definite_rejection_can_be_explicitly_retried_with_same_id(self):
        self.enqueue()
        self.reply = {"ok": False, "uncertain": False}
        self.box.step()
        self.assertEqual(self.box.status(TOKEN)["state"], "failed")
        self.box.step()
        self.assertEqual(self.calls.count("notify"), 1)
        self.assertTrue(self.box.retry_failed(TOKEN))
        self.reply = {"ok": True}
        self.box.step()
        self.assertEqual(self.box.status(TOKEN)["state"], "notified")
        self.assertEqual(self.calls.count("notify"), 2)
        self.assertFalse(self.box.retry_failed(TOKEN))

    def test_crash_recovery_recovers_saved_only_and_pauses_inflight(self):
        self.enqueue()
        self.box.update(TOKEN, "sending")
        next_token = "b" * 32
        atomic_json(self.root / (next_token + ".json"),
                    {"submissionId": next_token, "autoResumeRequested": True, "threadId": THREAD})
        wrong_token = "c" * 32
        atomic_json(self.root / (wrong_token + ".json"),
                    {"submissionId": wrong_token, "autoResumeRequested": True, "threadId": OTHER})
        restarted = Outbox(self.root, THREAD, self.box.bridge)
        self.assertEqual(restarted.status(TOKEN)["state"], "uncertain")
        self.assertEqual(restarted.status(next_token)["state"], "pending")
        self.assertEqual(restarted.status(wrong_token)["state"], "unknown")

    def test_fast_ack_survives_success_and_lost_reply(self):
        for reply in ({"ok": True}, {"ok": False, "uncertain": True}):
            self.enqueue()
            self.box.update(TOKEN, "pending")
            def bridge(data):
                if data["action"] == "status":
                    return {"ok": True, "active": False, "threadId": THREAD}
                self.box.update(TOKEN, "received")
                return reply
            self.box.bridge = bridge
            self.box.step()
            self.assertEqual(self.box.status(TOKEN)["state"], "received")

    def test_acknowledgement_is_bound_to_task_and_notification(self):
        self.enqueue()
        root = self.root.parent
        atomic_json(root / "session.json", {"threadId": THREAD, "test": False, "bind": "127.0.0.1",
                                           "port": 12345, "accessKey": "k" * 40, "pid": 1})
        with patch.dict(os.environ, {"CODEX_THREAD_ID": OTHER}):
            with self.assertRaises(ValueError):
                acknowledge(root, TOKEN)
        with patch.dict(os.environ, {"CODEX_THREAD_ID": THREAD}):
            with self.assertRaises(ValueError):
                acknowledge(root, TOKEN)
            self.box.update(TOKEN, "notified")
            acknowledge(root, TOKEN)
            self.assertEqual(self.box.status(TOKEN)["state"], "received")

    def test_root_binding_and_lease_prevent_second_receiver(self):
        for value in ("{broken", "null", "{}", "[]", '{"port":12345}'):
            (self.root / "session.json").write_text(value, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_session(self.root)
        check_binding({"threadId": THREAD, "test": False, "bind": "127.0.0.1"}, THREAD, False, "127.0.0.1")
        with self.assertRaises(ValueError):
            check_binding({"threadId": THREAD, "test": False, "bind": "127.0.0.1"}, OTHER, False, "127.0.0.1")
        lease = acquire(self.root)
        try:
            with self.assertRaises(OSError):
                acquire(self.root)
        finally:
            lease.close()


if __name__ == "__main__":
    unittest.main()
