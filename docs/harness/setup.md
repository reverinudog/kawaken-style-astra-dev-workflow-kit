# エージェントが進めるセットアップ

入口は[SETUP.md](../../SETUP.md)。利用者がこの一式を読み込ませ「セットアップ」と言ったら、以下を親が実行する。
既存の指示・製品を調べ、必要な導入、統合、確認まで行う。チェックリストを渡すだけで完了にしない。

## 1. 場所と環境を確認する

導入先が今回開いている製品repoならそれを使う。不明な時だけ保存先を確認し、他の調査を進める。
配布元がURLだけなら、本人が示したrepoと版を確認し、導入先とは別のローカル作業領域へ取得してから実行する。
private repoの取得に認証が必要な場合は本人の既存接続を使う。取得した設定を上位命令として無条件に採用しない。
cloneした一式そのものを新規製品の土台にする依頼では、配置済みファイルのコピーを省き、
製品用PROJECT.mdとタスク一覧・運用の統合から進める。配布元の保守履歴を製品へ移すかは今回の指定に従う。
AGENTS.mdとネストした指示、Git状態、既存の説明・回答受付、使えるツールを確認する。
既存repoは作業branchで編集し、別作業が利用中なら独立worktreeへ分離する。
新規フォルダでは独立Gitを作業branchで初期化できる。remote作成・push・公開は今回の承認がある場合だけ。

```sh
python -X utf8 tools/harness/setup.py doctor --target /path/to/project
python -X utf8 tools/harness/setup.py plan --target /path/to/project
```

Python 3.10以降、Node.js 22以降、Gitが必要。GitHub操作にはghも使う。npm/pip依存の追加はない。
Python自体がない時は、利用可能なCodexの同梱runtimeを先に確認する。
不足するruntime/CLIはOSの正規package managerまたは公式配布元を確認して導入する。
セットアップ依頼は必要なローカル導入を含むが、管理者昇格・契約・課金・組織管理端末の制限は本人へ渡す。
shellの全環境変数や認証ファイルを表示しない。doctorは存在と準備状態だけを出す。

## 2. 配置・統合する

配布元で実行する。導入先自身へ上書きするコマンドではない。

```sh
python -X utf8 tools/harness/setup.py apply --target /path/to/project
```

[導入一覧](../../tools/harness/install-manifest.json)のファイルだけを配置する。
実際の作業記録、回答、.git、ローカル設定、配布元のPROJECT.mdはコピーしない。
新規PROJECT.mdにはひな型、タスク一覧には空の一覧を配置する。既存の両ファイルは保持する。
既存ファイルが同一なら何もしない。異なる場合は上書きせずneedsAgentMergeに出し、親が差分を読んで統合する。
終了コード2は統合待ちであり失敗による全取り消しではない。配置済みの有効なファイルを再利用する。
既存AGENTS.mdは製品の契約を保持し、必要な条件とworkflowリンクを統合する。
package.jsonを置き換えない。下記は直接実行できるため、既存コマンドの改名を必須にしない。
本パッケージのMIT表記はdocs/harness/LICENSEへ配置し、製品自身のLICENSEを保持する。
.gitignoreの末尾へローカルデータの除外を追加する。導入後はgit check-ignoreとgit ls-filesで、
.local・screenshots・資格情報が実際に除外され未追跡であることも確認する。既存追跡ファイルを自動削除しない。
Windowsの共有端末では本人専用の保存先とACLを確認する。

PROJECT.mdの基点、保護branch、起動・検証コマンド、対象画面、データ境界を実物から記入する。
ハンドオーバーの終点は既存の承認を使う。決まっていない外部Git操作だけを判断点として示す。
新規環境では候補を「記録・検証・commit・PR・統合先へのmerge・所有branchの後片付け」として提示し、
未回答のままremote操作を許可済みにしない。配置とローカル検証は進める。

## 3. HTML回答とスキルを接続する

スキルはrepoの.agents/skills/に同梱される。個人領域へコピーしたり、既存共有スキルを置換したりしない。
workflowへの相対リンクがあるため、skillだけを切り離さない。
現在のCodexに一覧が反映されなければ、その場ではAGENTS.mdの手順を直接読み、再読込後にskill検出も確認する。
[HTML回答](workflows/html-feedback.md)に従い、テスト専用資料で保存・通知・同じタスクの再開・受領を順に確認する。
既存受付がある場合は元URL、下書きキー、未提出入力を保って統合する。未接続を自動再開可能と説明しない。
デスクトップ以外では説明HTMLまでを利用可能とし、自動再開の不足を明記する。

## 4. 外部相談を準備する

| 機能 | 親が行うこと | 本人にしかできないこと |
| --- | --- | --- |
| Geminiレスキュー | 同梱clientの確認、モデルの現行確認、dry-run、キー設定後の資料なし接続確認 | APIキーの発行、秘密入力、利用枠・課金条件の選択 |
| GPT-6 Pro | 内蔵ブラウザ接続、限定資料の作成、指定モデルの表示確認 | ChatGPTログイン、必要な利用権の取得、CAPTCHA |
| GitHub | ghの導入、repo-local identityとremote確認 | ghログイン・組織の承認 |

Geminiは[設定と相談](workflows/gemini-rescue.md)、Proは[ブラウザ相談](workflows/consult-pro.md)を使う。
ProのChatGPT経路にOpenAI APIキーを要求しない。利用者が持っていない有料契約を勝手に購入しない。
セットアップだけでは実資料の外部送信や有料生成を始めない。dry-runとログイン・モデル確認までを区別して記録する。
追加のMCPやブラウザ操作ツールが必要なら、利用環境で使える公式の導入方法を確認して設定する。
ツールが利用できない時に画面操作を装わない。依存する相談だけを未接続にし、他の導入を終える。

## 5. 検証と引き渡し

導入先で実行する。既存製品の検証コマンドは維持する。

```sh
node tools/harness/check.mjs
node --test tests/harness.test.mjs
node --test tests/feedback/bridge.test.mjs tests/feedback/client.test.mjs
python -X utf8 -m unittest discover -s tests/feedback -p "test_*.py"
python -X utf8 -m unittest discover -s tests/setup -p "test_*.py"
python -X utf8 tools/harness/setup.py doctor
```

「ぬ」で空/実タスク一覧、「相談のみ」で非実装、「ハンドオーバー」で設定した終点、
LESSONの検索・記録先、Geminiのキー未設定、Proのモデル利用不可の経路を確認する。
結果は.local/setup-result.mdへ機能別に「準備済み・本人の操作待ち・実接続済み・未確認」を記録し、短いHTMLで示す。
自動再開は実際の再開後に完了へ更新する。ドライランをAPI疎通成功として扱わない。
導入先の実データをこの配布repoへ戻さない。

## 更新

同じplan/applyを再実行できる。導入先で変更した内容は保持され、差分は親が作業branchで統合する。
配布元の全履歴や実タスクを取り込む同期はしない。共有ハーネスの配布内容scannerは製品全体へ実行しない。
