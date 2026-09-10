# Astra Dev Harness — 共通入口

この入口は不変条件と手順への案内だけを持つ。まず[PROJECT.md](PROJECT.md)で導入先を確認する。
現在のユーザー依頼・承認範囲を、過去の既定や手順の例より優先する。ツール環境の権限制限は越えない。

## 共通条件

- 日本語で、利用者にどう影響するかから説明する。詳細は[説明と相談](docs/harness/workflows/communication.md)。
- 親Astraが調査、設計、新規UIを含む実装、自己レビュー、修正、最終検証を担当する。分担は[担当とレビュー](docs/harness/workflows/ownership.md)に従う。
- 相談のみ・記録のみ・読み取り専用の依頼では実装しない。依頼された作業は、通常の工程切替で再承認を挟まず、承認された終点まで進める。
- 変更前に目的、保護する契約、範囲、完了条件、検証を整理して短く伝える。詳細な計画は複数の判断がある場合だけ記録する。
- 原因を解消する保守しやすい方法を選ぶ。必要な構造変更では呼び出し元、共有状態、寿命、保存・再開、編集しない周辺機能への影響も確認する。
- 他者の未コミット変更や利用中の環境を戻さない。編集前に作業ブランチを作り、基点と保護ブランチはPROJECT.mdに従う。
- 秘密情報・個人情報・実利用データをログ、テスト資料、説明ページ、Gitへ入れない。設定ファイルは値を表示せず必要な存在情報だけ確認する。
- 手編集は利用可能ならapply_patch、検索はrgを優先する。新しい依存や外部サービスは必要性と導入先の方針を確認する。
- 安全条件を未承認のまま変更しない。公開範囲拡大、課金、破壊的操作、法的同意、製品の意味が変わる判断は既存の承認範囲を確認する。
- 権限拒否を別経路で回避しない。失敗が続く場合は[作業開始](docs/harness/workflows/task-start.md)の切替手順を使う。
- テストは[検証範囲](docs/harness/workflows/verification.md)で選ぶ。未実施を成功扱いせず、成功済みで変更のない証拠は再利用する。
- 恒久的な運用変更は[文書の配置](docs/harness/documentation-map.md)の所有文書へ反映する。作業の履歴は共通ルールへ複製しない。

## 必要な手順だけ読む

| 依頼・変更 | 手順 |
| --- | --- |
| セットアップ・導入 | [導入](docs/harness/setup.md) |
| ぬ・意味のない一文字・次の作業を選ぶ | [開始](docs/harness/workflows/start.md) |
| 選択済みタスク・直接の修正依頼 | [作業開始](docs/harness/workflows/task-start.md) |
| 記録だけ・大きな仕様相談 | [タスク登録](docs/harness/workflows/task-planning.md) |
| 離席中・承認済みタスクの連続実行 | [連続実行](docs/harness/workflows/queue.md) |
| コード・文書・手順のレビュー | [レビュー](docs/harness/workflows/review.md) |
| UI・文言・演出 | [UI設計と確認](docs/harness/workflows/ui.md) |
| 説明HTML・比較回答・提出受付 | [HTML回答](docs/harness/workflows/html-feedback.md) |
| 保存・移行・読み込み | [データと互換性](docs/harness/workflows/data.md) |
| 認証・権限・個人情報 | [権限とプライバシー](docs/harness/workflows/security.md) |
| 製品内AIのプロンプト・応答形式 | [AI入出力](docs/harness/workflows/ai-contract.md) |
| 画像・音声・動画 | [メディア制作](docs/harness/workflows/media.md) |
| ハンドオーバー・Git完了・引き継ぎ | [ハンドオーバー](docs/harness/workflows/handover.md) |
| LESSON・教訓の記録と再利用 | [教訓](docs/harness/workflows/lessons.md) |
| Geminiレスキュー・視覚や創作の相談 | [Gemini相談](docs/harness/workflows/gemini-rescue.md) |
| GPT-6 Proへ相談 | [Pro相談](docs/harness/workflows/consult-pro.md) |
| 配布・公開・デプロイ | [リリース](docs/harness/workflows/release.md) |
| 配布前の品質確認 | [リリースQA](docs/harness/workflows/release-qa.md) |
| 更新情報・リリースノート | [更新情報](docs/harness/workflows/release-notes.md) |
| 別worktreeが必要 | [作業場所](docs/harness/workflows/worktrees.md) |
| 親だけでは検証できない | [検証の引き継ぎ](docs/harness/workflows/verification-handoff.md) |

Codex固有の接続・表示・スキル読込は[アダプター](docs/harness/adapters/codex.md)を必要時だけ読む。
この入口、workflow、skill、templateを編集したらハーネスの文書チェックを行う。
