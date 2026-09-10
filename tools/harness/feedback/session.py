"""Local session lifecycle. Run from the Codex task that should receive answers."""
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from review_server import Receiver, atomic_json, document, ID
from local_files import confined, private_dir, private_open, require_untracked_runtime

HERE = Path(__file__).resolve().parent


def current_task():
    value = os.environ.get("CODEX_THREAD_ID", "")
    if not re.fullmatch(r"[a-f0-9-]{36}", value):
        raise ValueError("現在のCodexタスクから実行してください。")
    return value


def load_session(root):
    try:
        meta = json.loads(confined(root, root / "session.json").read_text(encoding="utf-8"))
        if not isinstance(meta, dict):
            raise ValueError()
        valid = (
            isinstance(meta.get("threadId"), str) and (meta["threadId"] == "" or re.fullmatch(r"[a-f0-9-]{36}", meta["threadId"]))
            and isinstance(meta.get("bind"), str) and re.fullmatch(r"[0-9.]{7,15}", meta["bind"])
            and type(meta.get("port")) is int and 1 <= meta["port"] <= 65535
            and isinstance(meta.get("accessKey"), str) and re.fullmatch(r"[A-Za-z0-9_-]{32,128}", meta["accessKey"])
            and type(meta.get("test")) is bool
            and type(meta.get("pid")) is int and meta["pid"] > 0
        )
        if not valid:
            raise ValueError()
        return meta
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        raise ValueError("受付の起動記録を読み取れません。既存URLを維持するためsession.jsonを復旧してください。") from None


def request(meta, path="/api/health", post=False):
    origin = "http://" + meta["bind"] + ":" + str(meta["port"])
    headers = {"X-Feedback-Key": meta["accessKey"], "Origin": origin}
    with urlopen(Request(origin + path, data=b"" if post else None, headers=headers), timeout=3) as reply:
        return json.load(reply)


def check_binding(meta, thread, test, bind):
    if meta and (meta["threadId"] != thread or meta["test"] != test or meta["bind"] != bind):
        raise ValueError("この資料のタスク・接続先・テスト用途は固定です。別用途には新しい資料フォルダを使ってください。")


def acquire(root):
    handle = private_open(root / "receiver.lock", "a+b")
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            if not handle.read(1):
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise
    return handle


def serve(root, args):
    # Lock before constructing Outbox: a second process must not alter live delivery state.
    lease = acquire(root)
    config, _ = document(root)
    thread = current_task() if config.get("mode", "review") != "explain" else os.environ.get("CODEX_THREAD_ID", "")
    meta = load_session(root)
    check_binding(meta, thread, args.test, args.bind)
    if meta and args.port and args.port != meta["port"]:
        raise ValueError("既存URLを維持するため、保存済みポートを使用してください。")
    server = Receiver(root, args.bind, meta["port"] if meta else args.port,
                      thread, args.test, access_key=meta["accessKey"] if meta else None)
    atomic_json(root / "session.json", {
        "threadId": thread, "bind": args.bind, "port": server.server_port,
        "accessKey": server.access_key, "test": args.test, "pid": os.getpid(),
    })
    if server.queue:
        server.queue.start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
        lease.close()


def start(root, args):
    config, _ = document(root)
    thread = current_task() if config.get("mode", "review") != "explain" else os.environ.get("CODEX_THREAD_ID", "")
    meta = load_session(root)
    check_binding(meta, thread, args.test, args.bind)
    if meta:
        try:
            health = request(meta)
            if health["threadId"] != thread or health["test"] != args.test:
                raise ValueError("既存受付の接続先が一致しません。")
            if health["mode"] != config.get("mode", "review"):
                raise ValueError("表示形式の変更には、この資料の受付だけをstopしてstartしてください。")
            print(json.dumps({"url": url(meta), "reused": True}, ensure_ascii=False))
            return
        except (URLError, TimeoutError, OSError):
            pass
    command = [sys.executable, str(HERE / "session.py"), "serve", "--root", str(root),
               "--bind", args.bind, "--port", str(args.port)]
    if args.test:
        command.append("--test")
    with private_open(root / "receiver.log") as log:
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                 start_new_session=os.name != "nt")
    until = time.monotonic() + 15
    while time.monotonic() < until:
        if child.poll() is not None:
            raise ValueError("受付を起動できません。receiver.logを確認してください。回答と既存URLは保持しています。")
        meta = load_session(root)
        if meta:
            try:
                if request(meta)["threadId"] == thread:
                    print(json.dumps({"url": url(meta), "reused": False}, ensure_ascii=False))
                    return
            except (URLError, TimeoutError, OSError):
                pass
        time.sleep(0.2)
    raise ValueError("受付の起動を確認できません。receiver.logを確認してください。")


def url(meta):
    return "http://" + meta["bind"] + ":" + str(meta["port"]) + "/#key=" + meta["accessKey"]


def acknowledge(root, token):
    if not ID.fullmatch(token or ""):
        raise ValueError("提出番号を確認してください。")
    meta = load_session(root)
    if not meta or meta["threadId"] != current_task():
        raise ValueError("受領できるのは回答先と同じCodexタスクだけです。")
    folder = confined(root, root / ("test-submissions" if meta["test"] else "submissions"))
    saved = json.loads(confined(folder, folder / (token + ".json")).read_text(encoding="utf-8"))
    if saved.get("threadId") != meta["threadId"]:
        raise ValueError("回答の宛先が一致しません。")
    with sqlite3.connect(confined(folder, folder / "notifications.sqlite3")) as connection:
        count = connection.execute(
            "UPDATE jobs SET state='received',error=NULL,updated=? WHERE id=? AND state IN ('sending','notified','uncertain','received')",
            (time.time(), token)).rowcount
    if not count:
        raise ValueError("通知された回答を読んでから受領してください。")
    print(json.dumps({"received": token}))


def task_config(index, storage_key, explain=False):
    text = index.read_text(encoding="utf-8-sig")
    entries = re.findall(r"^- \[([^\]]+)\]\((tasks/[^)]+\.md)\)([^\n]*)", text, re.M)
    if len(re.findall(r"\]\(tasks/[^)]+\.md\)", text)) != len(entries):
        raise ValueError("タスク一覧を - [名前](tasks/name.md) の形式に整えてください。")
    names = [row[0] for row in entries]
    if len(set(names)) != len(names) or "今回は選ばない" in names or len(names) > 99:
        raise ValueError("一覧の重複・予約名・件数を確認してください。")
    for _, relative, _ in entries:
        target = index.parent / relative
        if not target.resolve().is_relative_to(index.parent.resolve() / "tasks") or not target.is_file() or "done" in Path(relative).parts:
            raise ValueError("一覧の有効な仕様ファイルへのリンクを確認してください。")
    mode = "explain" if explain or not entries else "choose"
    return {
        "mode": mode, "title": "次の作業を選ぶ" if entries else "タスク一覧", "storageKey": storage_key,
        "decisions": names + ["今回は選ばない"] if mode == "choose" else [],
        "commentRequired": [], "proposals": [{
            "id": "next-task", "title": "取り組みたいものを一つ選んでください" if mode == "choose" else "登録されているタスク" if entries else "未完了の登録タスクはありません",
            "after": "\n".join(row[0] + " " + row[2].strip() for row in entries) if entries else "新しい作業を頼むか、後で行うことをタスクとして記録できます。",
            "reason": "選択後に仕様を確認し、作業範囲と検証を整理します。" if mode == "choose" else "このページから回答の送信は行いません。",
        }],
    }


def refresh_tasks(root, args):
    if not args.tasks:
        raise ValueError("--tasksで一覧を指定してください。")
    thread = current_task()
    meta = load_session(root)
    if meta and meta["threadId"] != thread:
        raise ValueError("別タスクの資料を更新できません。")
    if (root / "feedback.json").exists():
        config, _ = document(root)
        if [x["id"] for x in config["proposals"]] != ["next-task"]:
            raise ValueError("タスク一覧以外の資料を置き換えられません。")
        storage_key = config["storageKey"]
    else:
        storage_key = "task-choice-" + thread
    new = task_config(Path(args.tasks).resolve(), storage_key, args.explain)
    if meta:
        try:
            health = request(meta)
            if health["mode"] != new["mode"]:
                raise ValueError("表示形式が変わります。同じ資料の受付だけをstopし、更新後にstartしてください。")
        except (URLError, TimeoutError, OSError):
            pass
    atomic_json(root / "feedback.json", new)
    document(root)
    print(json.dumps({"updated": True, "mode": new["mode"]}))


def init(root, args):
    if (root / "feedback.json").exists() or (root / "session.json").exists():
        raise ValueError("既存の資料は上書きしません。feedback.jsonを編集して同じURLを再読込してください。")
    if args.source:
        config = json.loads(Path(args.source).read_text(encoding="utf-8-sig"))
    elif args.tasks:
        index = Path(args.tasks).resolve()
        config = task_config(index, root.name + "-tasks", getattr(args, "explain", False))
    else:
        raise ValueError("--from または --tasks を指定してください。")
    atomic_json(root / "feedback.json", config)
    document(root)
    print(json.dumps({"created": str(root / "feedback.json")}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "tasks", "start", "serve", "status", "stop", "acknowledge"])
    parser.add_argument("--root", required=True)
    parser.add_argument("--from", dest="source")
    parser.add_argument("--tasks")
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--id")
    args = parser.parse_args()
    root = Path(args.root).absolute()
    # Runtime files belong in a designated folder, never the repository root.
    if (root / ".git").exists() or root == Path(root.anchor):
        raise ValueError(".local/feedback/資料名 のような専用フォルダを指定してください。")
    root = private_dir(root)
    require_untracked_runtime(root)
    if args.action == "init":
        init(root, args)
    elif args.action == "tasks":
        refresh_tasks(root, args)
    elif args.action == "start":
        start(root, args)
    elif args.action == "serve":
        serve(root, args)
    elif args.action == "acknowledge":
        acknowledge(root, args.id)
    else:
        meta = load_session(root)
        if not meta:
            raise ValueError("受付の起動記録がありません。")
        if args.action == "stop":
            if meta["threadId"] and meta["threadId"] != current_task():
                raise ValueError("別タスクの受付を停止できません。")
            print(json.dumps(request(meta, "/api/stop", post=True), ensure_ascii=False))
        else:
            print(json.dumps({**request(meta), "url": url(meta)}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, sqlite3.Error) as error:
        # Fixed messages only: no env values, raw JSON, submitted prose or pipe names.
        message = str(error) if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError) else "受付処理を完了できません。設定・接続・保存先を確認してください。"
        print(json.dumps({"error": message}, ensure_ascii=False))
        sys.exit(1)
