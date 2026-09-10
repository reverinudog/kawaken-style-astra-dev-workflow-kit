"""Create a bounded, local-only review bundle from explicit Git paths."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_files import confined, private_dir, private_open

from privacy import allowed_path, check_text, read_text


def git(root, *args):
    result = subprocess.run(["git", "--literal-pathspecs", "-C", str(root), *args], capture_output=True)
    if result.returncode:
        raise ValueError("Gitの対象・ref・ファイルを確認してください。")
    return result.stdout


def ref(root, value):
    if value.startswith("-"):
        raise ValueError("refを確認してください。")
    return git(root, "rev-parse", "--verify", value + "^{commit}").decode().strip()


def make_bundle(root, base, head, paths, requirements, working=False):
    root = root.resolve()
    base, head = ref(root, base), ref(root, head)
    if working and head != ref(root, "HEAD"):
        raise ValueError("未コミット差分のheadはHEADを指定してください。")
    check_text(requirements)
    if not requirements.strip() or not paths or len(paths) > 30 or len(set(paths)) != len(paths):
        raise ValueError("相談事項と重複しない対象ファイル（1〜30件）が必要です。")
    tree = {}
    for revision in (base, head):
        for entry in git(root, "ls-tree", "-r", "-z", revision).split(b"\0"):
            if entry:
                meta, name = entry.split(b"\t", 1)
                tree.setdefault(name.decode("utf-8"), []).append(meta.split(b" ")[0])
    indexed = set()
    if working:
        for entry in git(root, "ls-files", "--stage", "-z").split(b"\0"):
            if entry:
                meta, name = entry.split(b"\t", 1)
                mode, _, stage = meta.split(b" ")
                if stage != b"0":
                    raise ValueError("競合中のindexを相談資料へ混ぜられません。")
                indexed.add(name.decode("utf-8"))
                tree.setdefault(name.decode("utf-8"), []).append(mode)
    chunks = ["# 相談用の限定資料\n", "base: " + base, "head: " + head,
              "snapshot: " + ("working tree (uncommitted included)" if working else "committed"),
              "## 要件・相談事項\n" + requirements]
    for name in paths:
        if not allowed_path(name) or name not in tree or any(mode not in (b"100644", b"100755") for mode in tree[name]):
            raise ValueError("対象外・未追跡・機密名・リンク形式のファイルは同梱できません。")
        # Even a force-tracked ignored file must never become an outbound attachment.
        ignored = subprocess.run(["git", "-C", str(root), "check-ignore", "--no-index", "-q", "--", name], capture_output=True)
        if ignored.returncode == 0:
            raise ValueError("ignore対象のファイルは同梱できません。")
        if ignored.returncode != 1:
            raise ValueError("ignore設定を確認できません。")
        full = confined(root, root / name) if working else root / name
        if working and full.exists() and name not in indexed:
            raise ValueError("過去と同名でも、現在未追跡のファイルは同梱できません。")
        args = ["diff", "--no-ext-diff", "--no-textconv", "--no-renames", base]
        if not working:
            args.append(head)
        diff = git(root, *args, "--", name)
        if working:
            body = full.read_bytes() if full.exists() else b"(deleted)"
        else:
            exists = git(root, "ls-tree", "-z", head, "--", name)
            body = git(root, "show", head + ":" + name) if exists else b"(deleted)"
        if len(body) + len(diff) > 256 * 1024:
            raise ValueError("1ファイルの資料が大きすぎます。範囲を絞ってください。")
        try:
            text = diff.decode("utf-8") + "\n--- 現在の内容 ---\n" + body.decode("utf-8")
        except UnicodeError:
            raise ValueError("バイナリは同梱できません。") from None
        check_text(text)
        chunks.append("## " + name + "\n" + text)
    result = "\n\n".join(chunks) + "\n"
    if len(result.encode()) > 1024 * 1024:
        raise ValueError("資料全体が大きすぎます。範囲を絞ってください。")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", default=".")
    p.add_argument("--base", required=True)
    p.add_argument("--head", default="HEAD")
    p.add_argument("--path", action="append", required=True)
    p.add_argument("--requirements", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--working-tree", action="store_true")
    args = p.parse_args()
    root = Path(args.repo).resolve()
    out = args.output.absolute()
    out = confined(root, out)
    if not out.is_relative_to(root / ".local"):
        raise ValueError("資料の保存先はrepoの.local配下にしてください。")
    result = make_bundle(root, args.base, args.head, args.path, read_text(args.requirements), args.working_tree)
    private_dir(out.parent)
    with private_open(out, "xb") as handle:
        handle.write(result.encode("utf-8"))
    print(json.dumps({"saved": True, "files": len(args.path), "bytes": len(result.encode()), "sent": False}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        print(str(error) if type(error) is ValueError else "資料の作成に失敗しました。既存資料は上書きしません。", file=sys.stderr)
        sys.exit(1)
