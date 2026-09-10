"""Private runtime files and paths confined to an explicitly chosen directory."""
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess


def linked(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def confined(root, path):
    root, path = Path(root).absolute(), Path(path).absolute()
    if ".." in path.parts or linked(root):
        raise ValueError("リンク経由の保存先は利用できません。")
    base = root.resolve()
    try:
        relative = path.relative_to(root)
    except ValueError:
        # Callers may use a macOS system alias or Windows short path for an
        # already canonical root. Normalize ancestors above that root only.
        for parent in path.parents:
            if parent.resolve() == base and not linked(parent):
                relative = path.relative_to(parent)
                break
        else:
            raise ValueError("指定フォルダの外は利用できません。") from None
    # Resolve OS aliases above the chosen root (for example the macOS temp directory).
    full = base
    for part in relative.parts:
        full = full / part
        if linked(full):
            raise ValueError("リンク経由のファイルは利用できません。")
    if not full.resolve().is_relative_to(base):
        raise ValueError("指定フォルダの外は利用できません。")
    return full


def private_dir(path):
    path = Path(path)
    if linked(path):
        raise ValueError("保存フォルダにリンクは利用できません。")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.is_dir():
        raise ValueError("保存フォルダを確認してください。")
    if os.name != "nt":
        path.chmod(0o700)
    return path.resolve()


def require_untracked_runtime(path):
    """Outside Git is allowed; inside Git require ignored and untracked storage."""
    path = Path(path).absolute()
    if not path.is_dir():
        raise ValueError("保存専用の空フォルダを準備してからGitの除外を確認してください。")
    ancestor = path
    while not ancestor.exists():
        ancestor = ancestor.parent
    result = subprocess.run(["git", "-C", str(ancestor), "rev-parse", "--show-toplevel"], capture_output=True)
    if result.returncode:
        if any((p / ".git").exists() for p in (ancestor, *ancestor.parents)):
            raise ValueError("保存先のGit状態を確認できません。")
        return
    root = Path(os.fsdecode(result.stdout).strip()).resolve()
    relative = confined(root, path).relative_to(root).as_posix()
    tracked = subprocess.run(["git", "--literal-pathspecs", "-C", str(root), "ls-files", "-z", "--", relative], capture_output=True)
    # Check the existing directory itself. A representative filename can miss
    # negated session/submission paths; ignored directories exclude all children.
    ignored = subprocess.run(["git", "-C", str(root), "check-ignore", "--no-index", "-q", "--", relative], capture_output=True)
    if tracked.returncode or tracked.stdout or ignored.returncode != 0:
        raise ValueError("専用保存フォルダをGitのignore対象にし、既存の追跡ファイルがないことを確認してください。")


def private_open(path, mode="ab"):
    path = Path(path)
    path = confined(path.parent, path)
    if mode not in ("ab", "a+b", "xb"):
        raise ValueError("Unsupported private file mode")
    flags = os.O_RDWR if "+" in mode else os.O_WRONLY
    flags |= os.O_CREAT | (os.O_EXCL if mode == "xb" else os.O_APPEND)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("保存先は通常ファイルにしてください。")
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        return os.fdopen(fd, mode)
    except BaseException:
        os.close(fd)
        raise


def atomic_json(path, value):
    path = Path(path)
    path = confined(path.parent, path)
    temp = path.with_name("." + path.name + "." + secrets.token_hex(8) + ".tmp")
    try:
        with private_open(temp, "xb") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()
