# ハーネスを配布する前の確認

この文書は運用パッケージ自体の配布用。導入先製品は[リリース手順](workflows/release.md)を使う。

## 混入を防ぐ

出すファイルを選び、製品repoのclone、.git、素材、環境設定、過去の作業記録を複製しない。
新規の独立履歴を作る。製品固有の記述は単なる名前置換で済ませず、汎用的な手順として読み直す。
外部skillや素材の再配布条件が不明なものは同梱しない。

`node tools/harness/scan.mjs`はGitの対象ファイルと未追跡の非ignoreファイルを調べる。
`--staged`はindexそのもの、`--history`は全local refから到達するblobとcommit情報を調べる。
通常のworktree検査ではignoreされた未追跡ファイルは対象外だが、stage済みと履歴はignoreに関係なく確認する。

```sh
node tools/harness/scan.mjs
node tools/harness/scan.mjs --staged
node tools/harness/scan.mjs --history
```

元の作品名などは、この配布物の外にあるJSON配列へ記録して`--denylist /path/to/list.json`を追加できる。
禁止語そのものを配布repoへ保存しない。検査のエラーは一致した秘密の値を表示しない。

チェックは許可したテキスト形式、秘密値に似た書式、絶対パス、個人メールなどの検出を補助する。
自然文の製品仕様や未登録の秘密を網羅するものではない。全ファイルの内容レビューと併用する。
履歴検査の対象はlocalにあるref。remote全体を調べたことにはならない。

## Gitと公開設定

Gitのauthor / committerに使う名前とメールを確認する。
私用メールを避ける場合は、本人のGitHubアカウントで確認できるnoreplyをrepoローカルへ設定する。
globalのidentityを勝手に変更しない。
GitHubが生成するmergeの作者設定は別。PR作成時の仮マージにも私用メールが入る場合があるため、
PRの作成前にアカウント側の作者設定と、非公開の検証用repoでの仮マージidentityを確認する。
未確認なら公開候補ではPRを作らない。対応CLIの--author-emailへ確認済みnoreplyを明示し、
--match-head-commitへレビュー済みheadを指定する。生成後のauthor/committerも値を露出せず検査する。

承認済みのprivate repoへ送る直前に、remote URLとvisibilityを再取得する。
送信後にもprivateであること、branchとcommitが一致することを確認する。
最初のprivate保存はpublic化の承認を含まない。public化の前は履歴を含めて再監査し、
所有者がライセンスと公開対象を決める。
branchの履歴修正後もホストの旧PR参照・キャッシュを消去したことにはならない。
残存がある場合は公開前の未完条件として記録し、privateを維持する。
ホスト側で消去を確認できない場合は、監査済みスナップショットから新しい独立repoを作る方法もある。
既存repoをprivateで保持し、新repoをforkやmirrorにせず、履歴・PR・キャッシュを移さない。
旧repoの削除・公開、サポートへの連絡は別の承認がある場合だけ行う。

## 独立した公開候補を作る

```sh
node tools/harness/export.mjs --ref REVIEWED_COMMIT --output ../new-release-directory --denylist /path/to/list.json
```

指定commitの通常ファイルを全件検査してから、新しいフォルダへ書き出す。
未commitの編集、未追跡ファイル、.local、.gitは取り込まない。出力先が存在する場合は停止する。
.release-manifest.jsonへファイルごとのSHA-256を記録する。この一覧自体はハッシュ対象外。
一覧は書き出した時点の照合用で、以後の編集を自動認証する署名ではない。

新repoへ送る前に内容・license・作者情報を監査する。送信後は新規cloneから全remote branch/tag・PR参照を取得し、
内容と履歴を再検査する。PRを一度でも作ったrepoでは仮マージ・閉じたPRのSHAも確認する。
旧repoの問題SHAが新repoで取得できないこと、forkではないこと、privateであることも確認する。
自動CI・独立レビュー・修正後検証の結果を記録し、READMEの対応範囲と未確認事項を最後に更新する。

検査失敗時はpushを止めて原因を解消する。公開後の秘密漏えいは履歴削除だけで解決したことにせず、
所有者に事実を伝え、必要な無効化などを判断する。
