"""Explicit, one-shot Gemini consultation; dry-run never sends content."""
import argparse
import base64
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPRedirectHandler, build_opener

from privacy import read_text
from key import load_key
from local_files import confined, private_dir, private_open

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
DEFAULT_MODEL = "gemini-3.7-flash"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("APIの転送には追従しません。公式の接続先を確認してください。")


urlopen = build_opener(NoRedirect()).open


def request_json(req):
    try:
        with urlopen(req, timeout=180) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError("Geminiの応答が大きすぎます。")
        return json.loads(raw)
    except HTTPError as error:
        raise ValueError("Gemini HTTP " + str(error.code) + "。自動再送しません。認証・利用枠・モデルを確認してください。") from None
    except (URLError, TimeoutError, ValueError):
        # HTTP header/decoder exceptions may include credentials or response data.
        raise ValueError("Geminiの応答を確認できませんでした。自動再送は行いません。") from None


def image_block(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("画像は8MB以下の通常ファイルにしてください。")
    raw = path.read_bytes()
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif raw.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        raise ValueError("PNG・JPEG・WebPの実画像を指定してください。")
    return {"type": "image", "mime_type": mime, "data": base64.b64encode(raw).decode("ascii")}


def payload(prompt, images, model, role, thinking, max_output=4096):
    if not prompt.strip() or len(prompt.encode()) > 128 * 1024 or not re.fullmatch(r"gemini-[A-Za-z0-9.-]+", model):
        raise ValueError("相談文の長さとモデル名を確認してください。")
    if len(images) > 4 or (role == "visual" and not images):
        raise ValueError("視覚相談には実画面が必要です。画像は4枚までです。")
    if not 128 <= max_output <= 32768:
        raise ValueError("出力上限は128〜32768トークンにしてください。")
    instruction = ("あなたはゲーム・アプリ・Webサービスのデザイン相談相手です。実画像から読みやすさ、構図、操作の分かりやすさを評価してください。観測と推測を分け、問題の位置と具体的な改善案を示してください。" if role == "visual" else
                   "あなたは創作の相談相手です。依頼の目的と既に採用された条件を守り、複数の可能性と具体案を考えてください。")
    return {"model": model, "store": False, "system_instruction": instruction,
            "generation_config": {"thinking_level": thinking, "max_output_tokens": max_output},
            "input": [{"type": "text", "text": prompt}, *images]}


def extract(reply):
    if not isinstance(reply, dict) or reply.get("status") not in (None, "completed"):
        raise ValueError("Geminiの完了した応答を取得できませんでした。")
    if isinstance(reply.get("output_text"), str) and reply["output_text"].strip():
        return reply["output_text"].strip()
    result = []
    for step in reply.get("steps", []):
        if isinstance(step, dict) and step.get("type") == "model_output":
            for block in step.get("content", []):
                if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                    result.append(block["text"])
    if not result:
        raise ValueError("Geminiから本文を取得できませんでした。")
    return "\n".join(result)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prompt-file", type=Path)
    p.add_argument("--image", action="append", default=[], type=Path)
    p.add_argument("--role", choices=("visual", "creative"), default="visual")
    p.add_argument("--model", default=os.environ.get("GEMINI_RESCUE_MODEL", DEFAULT_MODEL))
    p.add_argument("--thinking", choices=("minimal", "low", "medium", "high"), default="high")
    p.add_argument("--send", action="store_true")
    p.add_argument("--check-connection", action="store_true", help="Read model metadata without sending a prompt or generating content")
    p.add_argument("--max-output-tokens", type=int, default=4096)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if args.check_connection:
        if args.send or args.prompt_file or args.image or args.output or not re.fullmatch(r"gemini-[A-Za-z0-9.-]+", args.model):
            raise ValueError("接続確認は資料を指定せず単独で実行してください。")
        key = load_key(Path.cwd().resolve())
        if not key:
            raise ValueError("APIキーが未設定です。")
        response = request_json(Request("https://generativelanguage.googleapis.com/v1beta/models/" + args.model,
                                        headers={"x-goog-api-key": key}))
        if not isinstance(response, dict) or response.get("name") != "models/" + args.model:
            raise ValueError("指定モデルの情報を確認できませんでした。")
        print(json.dumps({"connection": "verified", "model": args.model, "promptSent": False, "generationVerified": False}))
        return
    if not args.prompt_file:
        raise ValueError("--prompt-fileを指定してください。")
    body = payload(read_text(args.prompt_file), [image_block(x) for x in args.image], args.model, args.role, args.thinking, args.max_output_tokens)
    encoded = json.dumps(body, ensure_ascii=False).encode()
    if len(encoded) > 20 * 1024 * 1024:
        raise ValueError("送信資料が大きすぎます。画像を絞ってください。")
    if not args.send:
        print(json.dumps({"sent": False, "model": args.model, "images": len(args.image), "bytes": len(encoded), "sha256": hashlib.sha256(encoded).hexdigest(), "store": False, "maxOutputTokens": args.max_output_tokens}))
        return
    key = load_key(Path.cwd().resolve())
    if not key:
        raise ValueError("GEMINI_API_KEYが未設定です。セットアップ手順で秘密入力を設定してください。")
    if args.output:
        args.output = confined(Path.cwd(), args.output)
    if args.output and args.output.exists():
        raise ValueError("出力先が既に存在します。新しい.local配下の保存先を指定してください。")
    if args.output and not args.output.is_relative_to(Path.cwd().resolve() / ".local"):
        raise ValueError("出力先は.local配下にしてください。")
    req = Request(ENDPOINT, data=encoded, headers={"Content-Type": "application/json", "x-goog-api-key": key}, method="POST")
    answer = extract(request_json(req))
    answer = answer.replace(key, "[REDACTED]")
    if args.output:
        private_dir(args.output.parent)
        with private_open(args.output, "xb") as handle:
            handle.write((answer + "\n").encode("utf-8"))
        print(json.dumps({"saved": True, "sent": True, "model": args.model}))
    else:
        print(answer)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        print(str(error) if type(error) is ValueError else "相談処理に失敗しました。値を表示せず設定を確認してください。", file=sys.stderr)
        sys.exit(1)
