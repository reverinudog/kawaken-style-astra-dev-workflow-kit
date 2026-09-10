"""Allowlisted HTML receiver. Drafts stay in the browser; only submissions reach disk."""
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import sqlite3
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_files import atomic_json, confined, private_dir

from outbox import Outbox

HERE = Path(__file__).resolve().parent
ID = re.compile(r"^[a-zA-Z0-9-]{16,80}$")

class InvalidInput(ValueError):
    """Safe, fixed text suitable for display."""


def require(condition):
    if not condition:
        raise InvalidInput("feedback.jsonの設定を確認してください。")


def document(root):
    try:
        config = json.loads(confined(root, root / "feedback.json").read_text(encoding="utf-8-sig"))
        require(isinstance(config, dict))
        require(config.get("mode", "review") in ("explain", "review", "choose"))
        require(isinstance(config.get("title"), str) and config["title"].strip())
        require(isinstance(config.get("storageKey"), str) and config["storageKey"].strip())
        proposals = config["proposals"]
        require(isinstance(proposals, list) and 1 <= len(proposals) <= 100)
        seen = set()
        for p in proposals:
            require(isinstance(p, dict) and isinstance(p.get("id"), str) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", p["id"]))
            require(p["id"] not in seen)
            seen.add(p["id"])
            require(isinstance(p.get("title"), str))
            for key in ("before", "after", "reason"):
                require(key not in p or isinstance(p[key], str))
            if "steps" in p:
                require(isinstance(p["steps"], list) and 1 <= len(p["steps"]) <= 8)
                require(all(isinstance(step, str) for step in p["steps"]))
        decisions = config.get("decisions", [])
        if config.get("mode", "review") != "explain":
            require(isinstance(decisions, list) and 1 <= len(decisions) <= 100)
            require(all(isinstance(d, str) and d.strip() for d in decisions))
            require(len(set(decisions)) == len(decisions))
            require(isinstance(config.get("commentRequired", []), list))
            require(set(config.get("commentRequired", [])) <= set(decisions))
        require("page" not in config)  # Custom pages integrate with the client on their existing origin.
    except (AssertionError, OSError, ValueError, KeyError, TypeError):
        raise InvalidInput("feedback.jsonの設定を確認してください。") from None
    version = hashlib.sha256(json.dumps(config, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return config, version


class Receiver(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, root, bind="127.0.0.1", port=0, thread_id="", test=False, bridge=None, access_key=None):
        self.root = private_dir(root)
        self.config, _ = document(self.root)
        self.mode = self.config.get("mode", "review")
        try:
            address = ipaddress.ip_address(bind)
        except ValueError:
            raise InvalidInput("ローカルまたは承認済みのプライベートIPv4を指定してください。") from None
        networks = ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10")
        if address.version != 4 or not any(address in ipaddress.ip_network(net) for net in networks):
            raise ValueError("ローカルまたは承認済みのプライベートIPv4を指定してください。")
        self.bind = bind
        self.thread_id = thread_id
        self.test = test
        self.access_key = access_key or secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.out = self.root / ("test-submissions" if test else "submissions")
        self.queue = None
        if self.mode != "explain":
            if not thread_id:
                raise ValueError("回答受付には現在のタスクへの接続が必要です。")
            self.queue = Outbox(self.out, thread_id, bridge)
            status = self.queue.bridge({"action": "status"})
            if not status.get("ok") or status.get("threadId") != thread_id or not isinstance(status.get("active"), bool):
                raise ValueError("同じCodexタスクへの接続を確認できません。")
        super().__init__((bind, port), Handler)

    @property
    def origin(self):
        return "http://" + self.bind + ":" + str(self.server_port)

    @property
    def url(self):
        return self.origin + "/#key=" + self.access_key


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # No answers, request headers or access keys in logs.

    def send_bytes(self, status, content, kind):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(content)

    def reply(self, status, value):
        self.send_bytes(status, json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def host_ok(self):
        return self.headers.get("Host") == self.server.origin.removeprefix("http://")

    def access_ok(self):
        return hmac.compare_digest(self.headers.get("X-Feedback-Key", "").encode(), self.server.access_key.encode())

    def guard(self, write=False):
        if not self.host_ok() or (write and self.headers.get("Origin") != self.server.origin):
            self.reply(403, {"error": "この回答ページから操作してください。"})
            return False
        if not self.access_ok():
            self.reply(403, {"error": "接続用リンクからページを開いてください。"})
            return False
        return True

    def do_GET(self):
        parsed = urlsplit(self.path)
        if not self.host_ok():
            return self.reply(403, {"error": "接続先が一致しません。"})
        # Only the generic shell is public. Proposal content needs the session key.
        static = {"/": "page.html", "/index.html": "page.html", "/feedback-client.js": "client.js",
                  "/page.js": "page.js", "/page.css": "page.css"}
        if parsed.path in static:
            file = HERE / static[parsed.path]
            kinds = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}
            return self.send_bytes(200, file.read_bytes(), kinds[file.suffix] + "; charset=utf-8")
        if parsed.path not in ("/api/review", "/api/submission", "/api/events", "/api/health"):
            return self.reply(404, {"error": "見つかりません。"})
        if not self.guard():
            return
        if parsed.path == "/api/health":
            return self.reply(200, {"ok": True, "threadId": self.server.thread_id, "test": self.server.test, "mode": self.server.mode})
        if parsed.path == "/api/review":
            try:
                config, version = document(self.server.root)
                if config.get("mode", "review") != self.server.mode:
                    return self.reply(409, {"error": "表示形式が変わりました。受付を同じURLで再起動してください。"})
                return self.reply(200, {**config, "version": version, "autoResume": self.server.queue is not None, "test": self.server.test})
            except ValueError as error:
                return self.reply(400, {"error": str(error)})
        token = parse_qs(parsed.query).get("id", [""])[0]
        if not ID.fullmatch(token) or not self.server.queue:
            return self.reply(400, {"error": "提出番号を確認してください。"})
        if parsed.path == "/api/submission":
            return self.reply(200, {"notification": self.server.queue.status(token)})
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            previous = None
            while True:
                # The condition wakes on status changes; no browser polling or model task.
                with self.server.queue.changed:
                    state = self.server.queue.status(token)
                    if state != previous:
                        self.wfile.write((json.dumps({"notification": state}, ensure_ascii=False) + "\n").encode())
                        self.wfile.flush()
                        previous = state
                    if state["state"] in ("received", "failed", "uncertain", "unknown"):
                        break
                    self.server.queue.changed.wait(timeout=25)
                self.wfile.write(b"\n")  # Keepalive only; no delivery or model invocation.
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def do_POST(self):
        # Consume a bounded body before rejecting: unread bytes can reset Windows clients.
        raw_length = self.headers.get("Content-Length", "0")
        if not raw_length.isdecimal() or len(raw_length) > 8 or int(raw_length) > 300000:
            self.close_connection = True
            return self.reply(400, {"error": "回答のサイズを確認してください。"})
        self.connection.settimeout(10)
        try:
            raw_body = self.rfile.read(int(raw_length))
        except OSError:
            self.close_connection = True
            return
        if self.path not in ("/api/submit", "/api/stop", "/api/retry"):
            return self.reply(404, {"error": "送信先がありません。"})
        if not self.guard(write=True):
            self.close_connection = True
            return
        if self.path == "/api/stop":
            self.reply(200, {"stopping": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if not self.server.queue:
            return self.reply(405, {"error": "このページは説明用です。"})
        if self.path == "/api/retry":
            try:
                token = json.loads(raw_body).get("submissionId")
                if not isinstance(token, str) or not ID.fullmatch(token):
                    raise ValueError()
                if not self.server.queue.retry_failed(token):
                    return self.reply(409, {"error": "拒否が確定した通知だけを再試行できます。保存と受領の状況を確認してください。"})
                return self.reply(200, {"notification": self.server.queue.status(token)})
            except (ValueError, AttributeError):
                return self.reply(400, {"error": "提出番号を確認してください。"})
        with self.server.lock:
            try:
                length = int(raw_length)
                if not 0 < length <= 300000:
                    raise InvalidInput("回答のサイズを確認してください。")
                try:
                    body = json.loads(raw_body)
                except (ValueError, UnicodeError):
                    raise InvalidInput("回答の形式を確認してください。") from None
                config, version = document(self.server.root)
                if body.get("version") != version:
                    return self.reply(409, {"error": "資料が更新されています。入力は保持しています。再読込して確認してください。"})
                token = body.get("submissionId", "")
                if not isinstance(token, str) or not ID.fullmatch(token):
                    raise InvalidInput("提出番号を確認してください。")
                answers = body.get("answers")
                if not isinstance(answers, list) or len(answers) != len(config["proposals"]):
                    raise InvalidInput("全項目の回答を確認してください。")
                packed = []
                for proposal, answer in zip(config["proposals"], answers):
                    if answer.get("id") != proposal["id"] or answer.get("decision") not in config["decisions"]:
                        raise InvalidInput("未回答の項目があります。")
                    comment = answer.get("comment", "")
                    if not isinstance(comment, str) or len(comment) > 10000:
                        raise InvalidInput("コメントは10000文字以内です。")
                    if answer["decision"] in config.get("commentRequired", []) and not comment.strip():
                        raise InvalidInput("修正したい内容を入力してください。")
                    packed.append({**proposal, "decision": answer["decision"], "comment": comment})
                general = body.get("general", "")
                if not isinstance(general, str) or len(general) > 10000:
                    raise InvalidInput("全体コメントは10000文字以内です。")
                payload = {"reviewVersion": version, "answers": packed, "general": general}
                file = confined(self.server.root, self.server.out / (token + ".json"))
                if file.exists():
                    old = json.loads(file.read_text(encoding="utf-8"))
                    if old.get("threadId") != self.server.thread_id or old.get("test") != self.server.test or any(old.get(k) != v for k, v in payload.items()):
                        return self.reply(409, {"error": "同じ提出番号に別の回答は保存できません。"})
                    self.server.queue.enqueue(token, file)
                    return self.reply(200, {"saved": True, "submissionId": token, "savedAt": old["savedAt"], "notification": self.server.queue.status(token)})
                payload.update(submissionId=token, savedAt=datetime.now().astimezone().isoformat(),
                               autoResumeRequested=True, threadId=self.server.thread_id, test=self.server.test)
                atomic_json(file, payload)
                state = self.server.queue.enqueue(token, file)
                return self.reply(200, {"saved": True, "submissionId": token, "savedAt": payload["savedAt"], "notification": state})
            except InvalidInput as error:
                return self.reply(400, {"error": str(error)})
            except (ValueError, TypeError, AttributeError, KeyError):
                return self.reply(400, {"error": "回答の形式を確認してください。"})
            except (OSError, sqlite3.Error):
                return self.reply(500, {"error": "保存できませんでした。入力を保持して再試行してください。"})
