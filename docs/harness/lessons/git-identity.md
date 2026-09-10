# GitHubが作成するマージの作者情報

- 条件：ローカルでnoreplyを設定したうえで、GitHub側にmerge commitを作らせる。PR作成時の仮マージも含む。
- 観測：ローカルGit設定だけでは、GitHub側が選ぶ作者メールを制御できない。
- 原因：GitHubのアカウント設定と、ローカルrepoのidentityは別の設定。
- 次回の予防策：本人のnoreplyを確認し、対応するGitHub CLIではmerge時に`--author-email`を明示する。対象headを固定し、作成されたcommitのauthorとcommitterを送信後にも検査する。
- API側の拒否：正しい形式のnoreplyでもGitHub側が作者指定を受け付けない場合がある。私用メールや作者指定の省略へ切り替えない。アカウント側の設定・利用条件を確認する。承認済みのGit運用でレビュー済みheadをそのまま統合できる場合は、既存commitの作者情報を保持したfast-forwardも選べる。ブランチ保護やレビュー要件を迂回する許可にはしない。
- 復旧の限界：branchを書き換えても、古いSHAのPR参照・キャッシュが残ることがある。privateを維持し、公開前にホスト側の残存も確認する。
- 追加の予防策：PRを作る前にアカウント側の作者設定を確認し、非公開の検証用repoで仮マージのidentityを検証する。未確認の公開候補ではPR作成も避ける。PR headだけの取得では仮マージを調べたことにならない。公開候補を作り直す時はPR・fork・mirrorを使わず、監査済みファイルだけから独立履歴を作る。
- 正本：[ハンドオーバー](../workflows/handover.md)、[GitHubの履歴削除の説明](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)。

これは汎用的な再発防止策。特定アカウントのメールやリポジトリ識別子は記録しない。
