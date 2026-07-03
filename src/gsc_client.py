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


@dataclass
class GSCQueryRow:
    query: str
    clicks: int
    impressions: int
    ctr: float
    position: float


def _run_query(
    credentials: service_account.Credentials,
    site_url: str,
    start_date: date,
    end_date: date,
    dimensions: list[str],
    dimension_filter_groups: list[dict] | None = None,
) -> list[dict]:
    service = build("searchconsole", "v1", credentials=credentials)
    rows: list[dict] = []
    start_row = 0
    while True:
        body = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "dimensions": dimensions,
            "rowLimit": ROW_LIMIT,
            "startRow": start_row,
        }
        if dimension_filter_groups:
            body["dimensionFilterGroups"] = dimension_filter_groups
        response = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
        page_rows = response.get("rows", [])
        rows.extend(page_rows)
        if len(page_rows) < ROW_LIMIT:
            break
        start_row += ROW_LIMIT
    return rows


def fetch_page_metrics(
    credentials: service_account.Credentials,
    site_url: str,
    start_date: date,
    end_date: date,
) -> list[GSCPageRow]:
    """指定期間のページ別Search Console指標を取得する（rowLimitを超える場合はページネーション）。"""
    rows = _run_query(credentials, site_url, start_date, end_date, dimensions=["page"])
    return [
        GSCPageRow(
            path=urlparse(row["keys"][0]).path or "/",
            url=row["keys"][0],
            clicks=int(row.get("clicks", 0)),
            impressions=int(row.get("impressions", 0)),
            ctr=float(row.get("ctr", 0.0)),
            position=float(row.get("position", 0.0)),
        )
        for row in rows
    ]


def fetch_query_metrics(
    credentials: service_account.Credentials,
    site_url: str,
    start_date: date,
    end_date: date,
) -> list[GSCQueryRow]:
    """指定期間のサイト全体のキーワード(検索クエリ)別指標を取得する。"""
    rows = _run_query(credentials, site_url, start_date, end_date, dimensions=["query"])
    return [
        GSCQueryRow(
            query=row["keys"][0],
            clicks=int(row.get("clicks", 0)),
            impressions=int(row.get("impressions", 0)),
            ctr=float(row.get("ctr", 0.0)),
            position=float(row.get("position", 0.0)),
        )
        for row in rows
    ]


def fetch_query_metrics_for_page(
    credentials: service_account.Credentials,
    site_url: str,
    page_url: str,
    start_date: date,
    end_date: date,
) -> list[GSCQueryRow]:
    """指定ページに絞り込んだキーワード別指標を取得する（下落ページの原因分析用）。"""
    filter_groups = [
        {"filters": [{"dimension": "page", "operator": "equals", "expression": page_url}]}
    ]
    rows = _run_query(
        credentials,
        site_url,
        start_date,
        end_date,
        dimensions=["query"],
        dimension_filter_groups=filter_groups,
    )
    return [
        GSCQueryRow(
            query=row["keys"][0],
            clicks=int(row.get("clicks", 0)),
            impressions=int(row.get("impressions", 0)),
            ctr=float(row.get("ctr", 0.0)),
            position=float(row.get("position", 0.0)),
        )
        for row in rows
    ]
