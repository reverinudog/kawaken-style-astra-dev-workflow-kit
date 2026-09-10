# 変更する人へ

AGENTS.mdとPROJECT.mdを読み、作業branchで変更します。作品の仕様・実データ・個人用パスは持ち込みません。
新しい運用は対応するworkflowに置き、入口・skill・READMEは案内と利用者向けの説明に絞ります。

Python 3.10以降、Node.js 22以降、Gitで以下を実行できます。外部パッケージのインストールは不要です。

```sh
npm run docs:check
npm test
npm run test:feedback
npm run test:setup
npm run harness:scan
node tools/harness/scan.mjs --staged
node tools/harness/scan.mjs --history
```

ActionsでもWindows・macOS・Linuxに同じ検査を実行します。APIキーやデスクトップへの接続は使いません。
単体テスト成功は、実際のCodex自動再開や外部AIの生成成功を意味しません。接続を変えた時は合成資料で別途確認します。
変更が防ぐ不具合を示し、既存テストを活用・拡張します。同じ失敗を重複検査するために件数を増やしません。

依存物や外部のコードを追加する場合は、権利と再配布条件、導入先での必要性を確認します。
現在はNode.js/Pythonの標準機能とOSの保護機能を使い、追加の外部ライブラリの取得は不要です。
ハーネスのソース・文書・ひな型は[MITライセンス](LICENSE)です。外部AI、Codex、GitHubなどの利用条件は別です。
