# Codexでの利用

共通方針は[AGENTS.md](../../../AGENTS.md)、環境は[PROJECT.md](../../../PROJECT.md)。
ここには環境固有の差分だけを置く。

- 作業branchの既定prefixはcodex/。利用者の指定を優先する。
- 利用できる専用ツール、通常のshell、rg、apply_patchを用途に合わせて使う。
- 独立した読み取りはまとめて実行し、依存する編集・検証・Git操作は順序を守る。
- ブラウザは利用可能ならCodex内蔵を優先し、外部ブラウザの前面表示で作業を妨げない。
- 説明HTMLは利用可能なブラウザ表示機能で描画し、ファイルのリンクも添える。ソース表示だけを閲覧用資料の提示としない。
- 同じ説明ページは既存タブを再利用する。古い自作タブを閉じる時は未保存入力を確認する。
- HTML回答は[同梱受付](../workflows/html-feedback.md)を使う。デスクトップ接続を確認し、提出イベントから同じタスクを再開する。CLIや未接続環境で動くと仮定しない。
- 外部CLI、MCP、hook、共通スキルの存在を仮定しない。ユーザー全体の設定へ自動で書き込まない。
- 新しいサイドバーのタスク作成は明示依頼時だけ。内部レビューは[担当ルール](../workflows/ownership.md)に従う。

Astraの親担当やレビュー条件は、このハーネスの運用方針であってモデル性能の実証ではない。
特定の推論設定の強制や、トークン削減率の主張はしない。

スキル配置は[公式の説明](https://learn.chatgpt.com/docs/build-skills)、
指示ファイルの読込は[AGENTS.mdの公式説明](https://learn.chatgpt.com/docs/agent-configuration/agents-md)を参照。
Astraの指示・テスト範囲の留意点は[公式ガイド](https://developers.openai.com/api/docs/guides/latest-model#prompting-best-practices)も参考にする。
外部資料は製品固有の契約や今回のユーザー指示を上書きしない。
