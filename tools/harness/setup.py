"""Plan and apply an allowlisted install. Existing different files are preserved."""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
sys.path.insert(0, str(Path(__file__).resolve().parent))
from local_files import confined, linked

SOURCE = Path(__file__).resolve().parents[2]


def safe_child(root, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or not relative.parts or any(x in (".", "..") for x in relative.parts) or "\\" in name or ":" in name:
        raise ValueError("導入一覧の相対パスを確認してください。")
    return confined(root, root / name)


def assets(source):
    manifest = json.loads((source / "tools/harness/install-manifest.json").read_text(encoding="utf-8"))
    result = {}
    for name in manifest["files"]:
        if name in result:
            raise ValueError("導入一覧の重複を解消してください。")
        full = safe_child(source, name)
        if not full.is_file() or full.stat().st_size > 1024 * 1024:
            raise ValueError("導入ファイルの形式・サイズを確認してください。")
        result[name] = full.read_bytes()
    result["PROJECT.md"] = (source / "docs/harness/templates/project.md").read_bytes()
    # Retain this package's license without replacing the product's own license.
    license_file = source / "docs/harness/LICENSE" if (source / "docs/harness/LICENSE").exists() else source / "LICENSE"
    result["docs/harness/LICENSE"] = license_file.read_bytes()
    result["docs/harness/NEXT_TASKS.md"] = "# 次のタスク\n\n現在、未完了の登録タスクはありません。\n".encode()
    return result


IGNORE = (".local/", "screenshots/", "__pycache__/", "*.pyc", ".env", ".env.*")


def install(source, target, apply=False):
    if linked(target):
        raise ValueError("導入先の実フォルダを指定してください。")
    source, target = source.resolve(), target.resolve()
    if target == source or source.is_relative_to(target) or target.is_relative_to(source):
        raise ValueError("配布元と重ならない別の導入先を指定してください。")
    prepared = assets(source)
    ignore = safe_child(target, ".gitignore")
    old_ignore = ignore.read_bytes() if ignore.exists() else b""
    old_text = old_ignore.decode("utf-8-sig")
    # A later negation can cancel an existing line. Put protection after user rules.
    suffix = "# Astra local data\n" + "\n".join(IGNORE) + "\n"
    extra = [] if old_text.replace("\r\n", "\n").endswith(suffix) else list(IGNORE)
    prepared[".gitignore"] = old_ignore + (("\n# Astra local data\n" + "\n".join(extra) + "\n").encode() if extra else b"")
    plan = []
    for name, value in prepared.items():
        full = safe_child(target, name)
        if full.exists() and not full.is_file():
            raise ValueError("導入先に同名のディレクトリがあります。")
        current = full.read_bytes() if full.exists() else None
        status = "same" if current == value else "create" if current is None else "append" if name == ".gitignore" else "preserve" if name in ("PROJECT.md", "docs/harness/NEXT_TASKS.md") else "conflict"
        plan.append({"path": name, "status": status})
    if apply:
        # Validate the entire plan before any write. Never overwrite conflicting files.
        for item in plan:
            if item["status"] in ("create", "append"):
                full = safe_child(target, item["path"])
                full.parent.mkdir(parents=True, exist_ok=True)
                if item["status"] == "create":
                    with full.open("xb") as handle:
                        handle.write(prepared[item["path"]])
                else:
                    if full.read_bytes() != old_ignore:
                        raise ValueError("既存ignoreが変わりました。再度planを確認してください。")
                    with full.open("ab") as handle:
                        handle.write(prepared[item["path"]][len(old_ignore):])
    return {"applied": apply, "files": plan, "needsAgentMerge": [i["path"] for i in plan if i["status"] == "conflict"]}


def version(command, minimum):
    executable = shutil.which(command)
    if not executable:
        return {"state": "missing"}
    try:
        value = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=10)
        match = re.search(r"\b(?:v)?(\d+)\.(\d+)", value.stdout)
        pair = tuple(map(int, match.groups())) if match else (0, 0)
        return {"state": "ready" if value.returncode == 0 and pair >= minimum else "needs-update", "version": ".".join(map(str, pair))}
    except (OSError, subprocess.TimeoutExpired):
        return {"state": "unverified"}


def doctor(target):
    report = {"python": {"state": "ready" if sys.version_info >= (3, 10) else "needs-update", "version": str(sys.version_info.major) + "." + str(sys.version_info.minor)},
              "node": version("node", (22, 0)), "git": version("git", (2, 0)), "githubCli": version("gh", (2, 0))}
    report["desktop"] = {"state": "configured-unverified" if os.environ.get("CODEX_THREAD_ID") and os.environ.get("CODEX_APP_TOOLS_PIPE_PATH") else "missing"}
    report["gemini"] = {"state": "configured-unverified" if os.environ.get("GEMINI_API_KEY") or any((target / ".local/credentials" / x).is_file() for x in ("gemini.dpapi", "gemini.key")) else "key-required"}
    report["pro"] = {"state": "browser-login-and-model-check-required"}
    if report["githubCli"]["state"] == "ready":
        try:
            auth = subprocess.run(["gh", "auth", "status"], capture_output=True, timeout=15)
            report["githubAuth"] = {"state": "ready" if auth.returncode == 0 else "login-required"}
        except (OSError, subprocess.TimeoutExpired):
            report["githubAuth"] = {"state": "unverified"}
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("doctor", "plan", "apply"))
    p.add_argument("--target", type=Path, default=Path.cwd())
    args = p.parse_args()
    if args.target.is_symlink():
        raise ValueError("導入先のリンクは利用できません。")
    target = args.target.absolute()
    result = doctor(target) if args.action == "doctor" else install(SOURCE, target, args.action == "apply")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("needsAgentMerge"):
        sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        print(str(error) if type(error) is ValueError else "導入処理を完了できません。既存ファイルを保持して確認してください。", file=sys.stderr)
        sys.exit(1)
