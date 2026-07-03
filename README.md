# AIzen様サイト 週次GA4/サーチコンソールレポート

https://aizen-ai.co.jp/ のGA4・Search Consoleのページ別数値を集計し、毎週月曜(JST 9:00)にGoogle Chatへサマリを自動送信する。

## 構成
- `src/ga4_client.py`: GA4 Data APIからページ別指標を取得
- `src/gsc_client.py`: Search Console APIからページ別指標を取得
- `src/report.py`: 取得結果をマージし前週比を計算、Google Chat向けメッセージを組み立て
- `src/main.py`: エントリポイント（GitHub Actionsから実行される）
- `.github/workflows/weekly-report.yml`: 毎週月曜JST 9:00に実行するワークフロー

## 認証方式
GCPの組織ポリシーでサービスアカウントの鍵ファイル発行がブロックされているため、
**Workload Identity Federation** を使い、鍵ファイルなしでGitHub ActionsからGCPの
`aizen-report-bot@aizen-marketing-report.iam.gserviceaccount.com` へアクセスする。

構築済みの内容:
- GCPプロジェクト: `aizen-marketing-report`（プロジェクト番号 `609779181922`）
- Workload Identity プール: `github-pool` / プロバイダ: `github-provider`
- 許可対象: GitHubリポジトリ `khirai-coder/aizen-marketing-agent` のみ
- サービスアカウント: `aizen-report-bot` (GA4は閲覧者、Search Consoleはフルユーザーとして追加済み)

## GitHub Secretsに登録するもの
「Settings」→「Secrets and variables」→「Actions」に以下を登録する。

| Secret名 | 値 |
|---|---|
| `GA4_PROPERTY_ID` | `514596440` |
| `GSC_SITE_URL` | `sc-domain:aizen-ai.co.jp` |
| `GOOGLE_CHAT_WEBHOOK_URL` | Google Chatで発行したWebhook URL |

(Workload Identity Federationの接続先情報はSecretsではなく`.github/workflows/weekly-report.yml`に直接書いてある。秘密情報ではないため)

## グラフ画像の公開設定（初回のみ）
レポートに埋め込むページ別セッション数グラフは、GitHub Pagesで公開した画像をChatから参照する方式。
「Settings」→「Pages」→「Source」を `Deploy from a branch` にし、ブランチ `main` / フォルダ `/ (root)` を選んで保存する。
これで `https://khirai-coder.github.io/aizen-marketing-agent/reports/latest.png` が毎週上書き公開される。

## GitHub Actionsでの動作確認
Secrets登録後、GitHubリポジトリの「Actions」タブ →「Weekly GA4/GSC Report」→「Run workflow」で手動実行し、
ログとChatへの通知を確認する。

## 運用メモ
- 毎週対象になるのは「直近の完了週(月〜日)」。前週分との比較（前週比）を自動算出する
- GitHub共有ランナーの `schedule` トリガーは混雑時に実行が数十分〜遅延する場合がある
- 取得やChat送信に失敗した場合、可能な限りChatへエラー通知を送ってから異常終了する（Actions上は失敗として記録される）
