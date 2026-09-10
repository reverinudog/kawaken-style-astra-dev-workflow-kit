---
name: astra-html-feedback
description: Explain proposals in short HTML slides, collect item-by-item answers with drafts and batch submission, and resume the same Codex task after submission. Use for explanation pages, comparison reviews, task selection, and receiver recovery.
---

# astra-html-feedback

[共通入口](../../../AGENTS.md)と[説明と相談](../../../docs/harness/workflows/communication.md)を読み、
[HTML回答の手順](../../../docs/harness/workflows/html-feedback.md)に従う。

説明だけならexplain、採否ならreview、作業選択ならchooseを使う。
同梱の受付とクライアントを使い、今回の資料だけを.local/へ作成して描画した内蔵ブラウザを開く。
既存の承認済み受付・URL・保存キー・入力を保持する。共有済みページを別の入口へ勝手に切り替えない。
保存・通知受付・モデル受領を分け、初導入はテスト提出から同一タスク再開まで検証する。
接続がなければ入力を保持して修復する。未接続を自動受信できると説明しない。
