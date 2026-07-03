"""Search Console API からページ別指標を取得する。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from urllib.parse import urlparse

from google.oauth2 import service_account
from googleapiclient.discovery import build

ROW_LIMIT = 25000


@dataclass
class GSCPageRow:
    path: str
    url: str
    clicks: int
    impressions: int
    ctr: float
    position: float


def fetch_page_metrics(
    credentials: service_account.Credentials,
    site_url: str,
    start_date: date,
    end_date: date,
) -> list[GSCPageRow]:
    """指定期間のページ別Search Console指標を取得する（rowLimitを超える場合はページネーション）。"""
    service = build("searchconsole", "v1", credentials=credentials)

    rows: list[GSCPageRow] = []
    start_row = 0
    while True:
        response = (
            service.searchanalytics()
            .query(
                siteUrl=site_url,
                body={
                    "startDate": start_date.isoformat(),
                    "endDate": end_date.isoformat(),
                    "dimensions": ["page"],
                    "rowLimit": ROW_LIMIT,
                    "startRow": start_row,
                },
            )
            .execute()
        )
        page_rows = response.get("rows", [])
        for row in page_rows:
            url = row["keys"][0]
            rows.append(
                GSCPageRow(
                    path=urlparse(url).path or "/",
                    url=url,
                    clicks=int(row.get("clicks", 0)),
                    impressions=int(row.get("impressions", 0)),
                    ctr=float(row.get("ctr", 0.0)),
                    position=float(row.get("position", 0.0)),
                )
            )
        if len(page_rows) < ROW_LIMIT:
            break
        start_row += ROW_LIMIT
    return rows
