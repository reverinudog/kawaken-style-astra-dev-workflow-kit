"""User-operated masked key input. Never pass a key as a command argument."""
import argparse
import ctypes
import getpass
import os
import stat
import subprocess
import sys
import warnings
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_files import confined, private_dir, private_open


def key_path(root):
    path = root / ".local" / "credentials" / ("gemini.dpapi" if os.name == "nt" else "gemini.key")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("資格情報をプロジェクトの外へ配置できません。")
    return confined(root, path)


def crypt(raw, decrypt=False):
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]
    buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    source = Blob(len(raw), buffer)
    dest = Blob()
    api = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    api.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    api.restype = wintypes.BOOL
    if not api(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(dest)):
        raise ValueError("OSの資格情報保護を利用できません。")
    try:
        return ctypes.string_at(dest.pbData, dest.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(ctypes.cast(dest.pbData, ctypes.c_void_p))


def safe_path(path):
    confined(path.parent, path)


def validated(value):
    if not isinstance(value, str) or not value or len(value) > 4096 or not value.isascii() or any(ord(x) < 33 or ord(x) > 126 for x in value):
        raise ValueError("APIキーの形式を確認してください。値は表示しません。")
    return value


def load_key(root):
    existing = os.environ.get("GEMINI_API_KEY")
    if existing:
        return validated(existing)
    path = key_path(root)
    safe_path(path)
    if not path.exists():
        return ""
    if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("資格情報ファイルの権限を本人のみへ修正してください。")
    if path.stat().st_size > 16384:
        raise ValueError("資格情報ファイルを読み取れません。")
    raw = path.read_bytes()
    try:
        value = (crypt(raw, True) if os.name == "nt" else raw).decode("utf-8")
    except UnicodeError:
        raise ValueError("資格情報ファイルを読み取れません。") from None
    return validated(value)


def save_key(root, value):
    validated(value)
    path = key_path(root)
    safe_path(path)
    private_dir(path.parent)
    raw = crypt(value.encode()) if os.name == "nt" else value.encode()
    with private_open(path, "xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", default=".")
    args = p.parse_args()
    if not sys.stdin.isatty():
        raise ValueError("本人が操作する対話ターミナルで実行してください。チャットやコマンド引数へキーを貼らないでください。")
    root = Path(args.repo).resolve()
    relative = key_path(root).relative_to(root).as_posix()
    ignored = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", "--", relative], capture_output=True)
    tracked = subprocess.run(["git", "-C", str(root), "ls-files", "--", relative], capture_output=True)
    if ignored.returncode != 0 or tracked.returncode != 0 or tracked.stdout.strip():
        raise ValueError("先にセットアップを完了し、資格情報がGitの追跡対象外であることを確認してください。")
    if os.name != "nt":
        print("このPCの.local/credentialsへ、本人のみ読める平文ファイルとして保存します。環境変数を使う場合は中断してください。")
    else:
        print("このPCの.local/credentialsへ、Windowsの現在のユーザーで暗号化して保存します。")
    if key_path(root).exists():
        raise ValueError("既存キーを保持しています。上書きは行いません。")
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            value = getpass.getpass("Gemini API key (hidden): ")
        except getpass.GetPassWarning:
            raise ValueError("非表示入力を利用できる対話ターミナルで実行してください。") from None
    save_key(root, value)
    print("保存しました。キーの値は表示しません。API接続はまだ確認していません。")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        print(str(error) if type(error) is ValueError else "保存できません。既存キーは上書きしません。", file=sys.stderr)
        sys.exit(1)
