"""Small conservative checks, not a substitute for reviewing outbound material."""
import re
from pathlib import PurePosixPath


def allowed_path(name):
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in ("", ".", "..") for p in path.parts) or "\\" in name or ":" in name:
        return False
    forbidden = re.compile(r"(?:^\.env(?:\.|$)|secret|credential|token|password|^id_rsa$|^id_ed25519$)", re.I)
    if any(forbidden.search(part) or part in (".git", ".local", "screenshots", "node_modules") for part in path.parts):
        return False
    return path.suffix.lower() in {".md", ".txt", ".json", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".py", ".css", ".html", ".yaml", ".yml", ".toml", ".rs", ".go", ".cs", ".cpp", ".h"}


def check_text(text):
    patterns = (
        r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----",
        r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{25,}|AKIA[A-Z0-9]{16})\b",
        r"(?im)^\s*(?:GEMINI_API_KEY|OPENAI_API_KEY|API_KEY|PASSWORD|ACCESS_TOKEN)\s*[:=]\s*['\"]?[^\s'\"]{6,}",
        r"\b[A-Za-z]:[\\/](?![\\/])|/(?:Users|home)/[A-Za-z0-9_.-]+/",
    )
    if "\0" in text or any(re.search(p, text) for p in patterns):
        raise ValueError("送信資料に秘密値・個人パスの疑いがあります。必要な範囲を匿名化してください。")


def read_text(path, limit=1024 * 1024):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("資料は上限内の通常のテキストファイルを指定してください。")
    try:
        value = path.read_text(encoding="utf-8-sig")
    except UnicodeError:
        raise ValueError("資料のUTF-8形式を確認してください。") from None
    check_text(value)
    return value
