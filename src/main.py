"""週次GA4/Search Consoleレポートを取得しGoogle Chatへ送信するエントリポイント。"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import google.auth
import requests
from dotenv import load_dotenv

import ga4_client
import gsc_client
from report import build_chat_message, build_keyword_memo, build_report

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/webmasters.readonly",
]


def _load_credentials():
    """Application Default Credentials を使う。

    GitHub Actions では google-github-actions/auth (Workload Identity Federation)
    が実行前にADCを用意するため、鍵ファイルは不要。
    """
    credentials, _ = google.auth.default(scopes=SCOPES)
    return credentials


def _last_two_full_weeks(today: date) -> tuple[tuple[date, date], tuple[date, date]]:
    """基準日から見て直近の完了週(月〜日)と、その前の週を返す。"""
    this_week_monday = today - timedelta(days=today.weekday())
    last_week_monday = this_week_monday - timedelta(days=7)
    last_week_sunday = this_week_monday - timedelta(days=1)
    prev_week_monday = last_week_monday - timedelta(days=7)
    prev_week_sunday = last_week_monday - timedelta(days=1)
    return (last_week_monday, last_week_sunday), (prev_week_monday, prev_week_sunday)


def _notify_error(webhook_url: str | None, message: str) -> None:
    if not webhook_url:
        return
    try:
        requests.post(webhook_url, json={"text": f"⚠️ 週次レポート生成に失敗しました: {message}"}, timeout=30)
    except requests.RequestException:
        pass


def main() -> int:
    webhook_url = os.environ.get("GOOGLE_CHAT_WEBHOOK_URL")
    try:
        property_id = os.environ["GA4_PROPERTY_ID"]
        site_url = os.environ["GSC_SITE_URL"]
        webhook_url = os.environ["GOOGLE_CHAT_WEBHOOK_URL"]

        credentials = _load_credentials()

        tz_name = os.environ.get("REPORT_TIMEZONE", "Asia/Tokyo")
        today = datetime.now(ZoneInfo(tz_name)).date()

        period, prev_period = _last_two_full_weeks(today)

        current_ga4 = ga4_client.fetch_page_metrics(credentials, property_id, *period)
        prev_ga4 = ga4_client.fetch_page_metrics(credentials, property_id, *prev_period)
        current_gsc = gsc_client.fetch_page_metrics(credentials, site_url, *period)
        prev_gsc = gsc_client.fetch_page_metrics(credentials, site_url, *prev_period)
        ga4_totals_current = ga4_client.fetch_site_totals(credentials, property_id, *period)
        ga4_totals_prev = ga4_client.fetch_site_totals(credentials, property_id, *prev_period)

        report = build_report(
            period,
            prev_period,
            current_ga4,
            prev_ga4,
            current_gsc,
            prev_gsc,
            ga4_totals_current,
            ga4_totals_prev,
        )

        current_queries = gsc_client.fetch_query_metrics(credentials, site_url, *period)
        prev_queries = gsc_client.fetch_query_metrics(credentials, site_url, *prev_period)

        loser_page_queries = {}
        for _pct, cur, _prev_sessions in report["top_losers"]:
            if not cur.url:
                continue
            loser_page_queries[cur.path] = (
                gsc_client.fetch_query_metrics_for_page(credentials, site_url, cur.url, *period),
                gsc_client.fetch_query_metrics_for_page(credentials, site_url, cur.url, *prev_period),
            )

        memo_lines = build_keyword_memo(
            current_queries, prev_queries, report["top_losers"], loser_page_queries
        )
        message = build_chat_message(report, memo_lines)

        response = requests.post(webhook_url, json=message, timeout=30)
        response.raise_for_status()
        print(f"Report sent for {period[0]}〜{period[1]}")
        return 0
    except Exception as exc:  # noqa: BLE001 - 実行失敗を確実にChatへ通知する
        _notify_error(webhook_url, str(exc))
        print(f"Error: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    sys.exit(main())
