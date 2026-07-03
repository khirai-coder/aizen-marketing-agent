"""GA4 Data API からページ別指標を取得する。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Metric,
    RunReportRequest,
)
from google.oauth2 import service_account

METRICS = ["sessions", "activeUsers", "screenPageViews", "conversions"]


@dataclass
class GA4PageRow:
    path: str
    title: str
    sessions: int
    active_users: int
    page_views: int
    conversions: float


@dataclass
class GA4Totals:
    sessions: int
    active_users: int
    page_views: int
    conversions: float


def _client(credentials: service_account.Credentials) -> BetaAnalyticsDataClient:
    return BetaAnalyticsDataClient(credentials=credentials)


def fetch_site_totals(
    credentials: service_account.Credentials,
    property_id: str,
    start_date: date,
    end_date: date,
) -> GA4Totals:
    """サイト全体の合計指標を取得する。

    ページ別(pagePath)で内訳を取ってからsessions/activeUsersを単純合計すると、
    複数ページを見た1セッションが各ページで重複計上され水増しされるため、
    全体サマリはディメンションなしのレポートで別途取得する。
    """
    client = _client(credentials)
    request = RunReportRequest(
        property=f"properties/{property_id}",
        metrics=[Metric(name=m) for m in METRICS],
        date_ranges=[
            DateRange(start_date=start_date.isoformat(), end_date=end_date.isoformat())
        ],
    )
    response = client.run_report(request)
    if not response.rows:
        return GA4Totals(sessions=0, active_users=0, page_views=0, conversions=0.0)

    sessions, active_users, page_views, conversions = (
        v.value for v in response.rows[0].metric_values
    )
    return GA4Totals(
        sessions=int(sessions),
        active_users=int(active_users),
        page_views=int(page_views),
        conversions=float(conversions),
    )


def fetch_page_metrics(
    credentials: service_account.Credentials,
    property_id: str,
    start_date: date,
    end_date: date,
) -> list[GA4PageRow]:
    """指定期間のページ別GA4指標を取得する。"""
    client = _client(credentials)
    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="pagePath"), Dimension(name="pageTitle")],
        metrics=[Metric(name=m) for m in METRICS],
        date_ranges=[
            DateRange(start_date=start_date.isoformat(), end_date=end_date.isoformat())
        ],
        limit=100000,
    )
    response = client.run_report(request)

    rows: list[GA4PageRow] = []
    for row in response.rows:
        path = row.dimension_values[0].value
        title = row.dimension_values[1].value
        sessions, active_users, page_views, conversions = (
            v.value for v in row.metric_values
        )
        rows.append(
            GA4PageRow(
                path=path,
                title=title,
                sessions=int(sessions),
                active_users=int(active_users),
                page_views=int(page_views),
                conversions=float(conversions),
            )
        )
    return rows
