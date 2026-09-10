# 文書の配置

| 場所 | 所有する内容 |
| --- | --- |
| [共通入口](../../AGENTS.md) | 不変条件・workflowへの案内 |
| [導入入口](../../SETUP.md)・[セットアップ](setup.md) | エージェントによる環境準備・配置・統合・接続確認 |
| [プロジェクト設定](../../PROJECT.md) | 環境、基点、実行方法、権限、保護契約 |
| [Codexアダプター](adapters/codex.md) | 利用する環境の差分 |
| workflows/ | 実行時の判断と手順 |
| [.agents/skills](../../.agents/skills) | 手順の短い入口。本文はworkflowに置く |
| templates/ | 記入用の骨格 |
| [タスク一覧](NEXT_TASKS.md)・tasks/ | 今回の範囲、判断、受け入れ条件、結果 |
| [LESSONS](LESSONS.md)・lessons/ | 再発条件と対策。開始時に関連項目を読み、引き継ぎ時に更新 |
| 製品側のspec/design | 製品の動作・データ・画面の正本。ここに複製しない |
| [検査ツール](../../tools/harness) | 機械的に検証できる条件 |
| [HTML受付](../../tools/harness/feedback) | 表示・回答保存・通知待ち・環境接続 |
| [外部相談ツール](../../tools/harness/advice) | 限定資料・Gemini画像相談・本人による秘密入力 |
| .local/feedback/ | 利用中の資料・回答・通知状態。Git管理外 |

入口→今回の依頼→該当workflow→必要な設計資料・教訓の順で読む。
最初から全workflowや全教訓を読み込まない。変更のない文書や成功した検証は同じ作業中に再利用する。

更新は所有文書へ一度だけ行う。技能の入口へworkflow本文を複製しない。
導入先の製品仕様やローカル情報を、共有ハーネスへ逆流させない。
