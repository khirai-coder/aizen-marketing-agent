# AIzen様サイト 週次GA4/サーチコンソールレポート

https://aizen-ai.co.jp/ のGA4・Search Consoleのページ別数値を集計し、毎週月曜(JST 9:00)にGoogle Chatへサマリを自動送信する。

## 構成
- `src/ga4_client.py`: GA4 Data APIからページ別指標を取得
- `src/gsc_client.py`: Search Console APIからページ別指標を取得
- `src/report.py`: 取得結果をマージし前週比を計算、Google Chat向けメッセージを組み立て
- `src/main.py`: エントリポイント（GitHub Actionsから実行される）
- `.github/workflows/weekly-report.yml`: 毎週月曜JST 9:00に実行するワークフロー

## 事前準備（初回のみ）

### 1. GCPプロジェクト作成 & API有効化
1. [Google Cloud Console](https://console.cloud.google.com/) で新規プロジェクトを作成
2. 「APIとサービス」→「ライブラリ」から以下を有効化
   - Google Analytics Data API
   - Google Search Console API

### 2. サービスアカウント作成
1. 「APIとサービス」→「認証情報」→「認証情報を作成」→「サービスアカウント」
2. 名前は任意（例: `aizen-report-bot`）。ロール付与は不要（GA4/GSC側で個別に権限を渡すため）
3. 作成後、サービスアカウントの「鍵」タブから JSON形式の鍵を作成・ダウンロード
4. サービスアカウントのメールアドレス（`xxxx@yyyy.iam.gserviceaccount.com`）を控える

### 3. GA4にサービスアカウントを追加
1. GA4管理画面 →「管理」→ 対象プロパティの「プロパティのアクセス管理」
2. サービスアカウントのメールアドレスを「閲覧者」として追加
3. 「プロパティの設定」からプロパティID（数字のみ）を控える

### 4. Search Consoleにサービスアカウントを追加
1. Search Console → 対象プロパティ（aizen-ai.co.jp）の「設定」→「ユーザーとアクセス権」
2. サービスアカウントのメールアドレスを追加（権限は「フル」で問題なし）
3. プロパティが「ドメインプロパティ」の場合は `GSC_SITE_URL` に `sc-domain:aizen-ai.co.jp`、
   「URLプレフィックス」の場合は `https://aizen-ai.co.jp/` を使用

### 5. Google Chat Webhookを発行
1. レポートを送りたいGoogle Chatのスペースを開く
2. スペース名の横のメニュー →「アプリと連携機能を管理」→「Webhookを追加」
3. 名前を付けて作成し、発行されたWebhook URLを控える

### 6. GitHubリポジトリへSecretsを登録
このディレクトリをGitHubリポジトリにpushした上で、
「Settings」→「Secrets and variables」→「Actions」に以下を登録する。

| Secret名 | 値 |
|---|---|
| `GA4_PROPERTY_ID` | GA4のプロパティID（数字） |
| `GSC_SITE_URL` | `https://aizen-ai.co.jp/` または `sc-domain:aizen-ai.co.jp` |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | ダウンロードしたJSON鍵の中身をそのまま貼り付け |
| `GOOGLE_CHAT_WEBHOOK_URL` | 発行したWebhook URL |

## ローカルでの動作確認
```bash
cp .env.example .env
# .env の値を埋める（GOOGLE_SERVICE_ACCOUNT_JSONは1行のJSON文字列として貼り付け）
pip install -r requirements.txt
cd src
python main.py
```
実行後、Chatにレポートが届けば成功。

## GitHub Actionsでの動作確認
Secrets登録後、GitHubリポジトリの「Actions」タブ →「Weekly GA4/GSC Report」→「Run workflow」で手動実行し、
ログとChatへの通知を確認する。

## 運用メモ
- 毎週対象になるのは「直近の完了週(月〜日)」。前週分との比較（前週比）を自動算出する
- GitHub共有ランナーの `schedule` トリガーは混雑時に実行が数十分〜遅延する場合がある
- 取得やSlack送信に失敗した場合、可能な限りChatへエラー通知を送ってから異常終了する（Actions上は失敗として記録される）
