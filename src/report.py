"""GA4/GSCの取得結果をマージし、Google Chat向けのレポートを組み立てる。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ga4_client import GA4PageRow, GA4Totals
from gsc_client import GSCPageRow

TOP_N = 8
MOVERS_N = 3
NEW_PAGE_THRESHOLD = 5  # 前週がこの値未満なら%表示ではなく「新規」扱いにする


@dataclass
class PageMetrics:
    path: str
    title: str
    sessions: int = 0
    active_users: int = 0
    page_views: int = 0
    conversions: float = 0.0
    clicks: int = 0
    impressions: int = 0
    ctr: float = 0.0
    position: float = 0.0


def _merge(ga4_rows: list[GA4PageRow], gsc_rows: list[GSCPageRow]) -> dict[str, PageMetrics]:
    pages: dict[str, PageMetrics] = {}
    for r in ga4_rows:
        pages[r.path] = PageMetrics(
            path=r.path,
            title=r.title,
            sessions=r.sessions,
            active_users=r.active_users,
            page_views=r.page_views,
            conversions=r.conversions,
        )
    for r in gsc_rows:
        m = pages.get(r.path)
        if m is None:
            m = PageMetrics(path=r.path, title=r.path)
            pages[r.path] = m
        m.clicks = r.clicks
        m.impressions = r.impressions
        m.ctr = r.ctr
        m.position = r.position
    return pages


def _pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return (current - previous) / previous * 100


def _fmt_pct(pct: float | None) -> str:
    if pct is None:
        return "―"
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}%"


def _fmt_page_change(current: int, previous: int) -> str:
    """ページ単位のセッション変化を表示用文字列にする。

    前週がほぼゼロの場合、%表示だと前週1→今週233のようなケースで
    +23200%といった意味のない数字になるため「新規」扱いにする。
    """
    if previous < NEW_PAGE_THRESHOLD:
        return "新規" if current >= NEW_PAGE_THRESHOLD else "―"
    return _fmt_pct(_pct_change(current, previous))


def build_report(
    period: tuple[date, date],
    prev_period: tuple[date, date],
    current_ga4: list[GA4PageRow],
    prev_ga4: list[GA4PageRow],
    current_gsc: list[GSCPageRow],
    prev_gsc: list[GSCPageRow],
    ga4_totals_current: GA4Totals,
    ga4_totals_prev: GA4Totals,
) -> dict:
    """マージ済みページ指標と全体サマリを含むレポートデータを返す。"""
    current_pages = _merge(current_ga4, current_gsc)
    prev_pages = _merge(prev_ga4, prev_gsc)

    # セッション/ユーザーはページ内訳の合計だとGA4のデータ間引き(thresholding)で
    # 実際より少なく出ることがあるため、全体サマリはディメンションなしで取得した
    # ga4_totals_* を使う。クリック/表示回数(GSC)はページ内訳の合計で正確。
    totals_current = {
        "sessions": ga4_totals_current.sessions,
        "active_users": ga4_totals_current.active_users,
        "conversions": ga4_totals_current.conversions,
        "clicks": sum(p.clicks for p in current_pages.values()),
        "impressions": sum(p.impressions for p in current_pages.values()),
    }
    totals_prev = {
        "sessions": ga4_totals_prev.sessions,
        "active_users": ga4_totals_prev.active_users,
        "conversions": ga4_totals_prev.conversions,
        "clicks": sum(p.clicks for p in prev_pages.values()),
        "impressions": sum(p.impressions for p in prev_pages.values()),
    }

    top_pages = sorted(
        current_pages.values(), key=lambda p: p.sessions, reverse=True
    )[:TOP_N]

    # 前週にほぼ実績がなかったページ(新規公開など)は%変化が意味を持たないため、
    # 「新規で伸びたページ」として別枠にし、既存ページの増減(movers)からは除外する。
    new_pages = []
    movers = []
    for path, cur in current_pages.items():
        prev = prev_pages.get(path)
        prev_sessions = prev.sessions if prev else 0
        if prev_sessions < NEW_PAGE_THRESHOLD:
            if cur.sessions >= NEW_PAGE_THRESHOLD:
                new_pages.append(cur)
            continue
        if cur.sessions < 10 and prev_sessions < 10:
            continue
        pct = _pct_change(cur.sessions, prev_sessions)
        if pct is None:
            continue
        movers.append((pct, cur, prev_sessions))
    new_pages.sort(key=lambda p: p.sessions, reverse=True)
    movers.sort(key=lambda x: x[0], reverse=True)
    top_gainers = [m for m in movers if m[0] > 0][:MOVERS_N]
    top_losers = [m for m in movers if m[0] < 0][-MOVERS_N:][::-1]

    return {
        "period": period,
        "prev_period": prev_period,
        "totals_current": totals_current,
        "totals_prev": totals_prev,
        "top_pages": top_pages,
        "prev_pages": prev_pages,
        "new_pages": new_pages[:MOVERS_N],
        "top_gainers": top_gainers,
        "top_losers": top_losers,
    }


def build_chat_message(report: dict) -> dict:
    """Google Chat Webhook向けのcardsV2メッセージを組み立てる。"""
    start, end = report["period"]
    prev_start, prev_end = report["prev_period"]
    totals_current = report["totals_current"]
    totals_prev = report["totals_prev"]

    summary_lines = [
        f"<b>セッション</b>: {totals_current['sessions']:,} ({_fmt_pct(_pct_change(totals_current['sessions'], totals_prev['sessions']))})",
        f"<b>ユーザー</b>: {totals_current['active_users']:,} ({_fmt_pct(_pct_change(totals_current['active_users'], totals_prev['active_users']))})",
        f"<b>コンバージョン</b>: {totals_current['conversions']:.0f} ({_fmt_pct(_pct_change(totals_current['conversions'], totals_prev['conversions']))})",
        f"<b>クリック(検索)</b>: {totals_current['clicks']:,} ({_fmt_pct(_pct_change(totals_current['clicks'], totals_prev['clicks']))})",
        f"<b>表示回数(検索)</b>: {totals_current['impressions']:,} ({_fmt_pct(_pct_change(totals_current['impressions'], totals_prev['impressions']))})",
    ]

    top_lines = []
    for i, p in enumerate(report["top_pages"], start=1):
        prev = report["prev_pages"].get(p.path)
        prev_sessions = prev.sessions if prev else 0
        pct = _fmt_page_change(p.sessions, prev_sessions)
        top_lines.append(
            f"{i}. <b>{p.path}</b> — セッション {p.sessions:,} ({pct}) / クリック {p.clicks:,} / 掲載順位 {p.position:.1f}"
        )

    mover_lines = []
    if report.get("new_pages"):
        mover_lines.append("<b>新規で伸びたページ</b>")
        for p in report["new_pages"]:
            mover_lines.append(f"・{p.path} — セッション {p.sessions:,}")
    if report["top_gainers"]:
        mover_lines.append("<b>伸びたページ</b>")
        for pct, cur, prev_sessions in report["top_gainers"]:
            mover_lines.append(f"・{cur.path} — {prev_sessions:,} → {cur.sessions:,} ({_fmt_pct(pct)})")
    if report["top_losers"]:
        mover_lines.append("<b>落ち込んだページ</b>")
        for pct, cur, prev_sessions in report["top_losers"]:
            mover_lines.append(f"・{cur.path} — {prev_sessions:,} → {cur.sessions:,} ({_fmt_pct(pct)})")

    sections = [
        {
            "header": "全体サマリ",
            "widgets": [{"textParagraph": {"text": "<br>".join(summary_lines)}}],
        }
    ]
    if top_lines:
        sections.append(
            {
                "header": "ページ別ランキング（セッション順）",
                "widgets": [{"textParagraph": {"text": "<br>".join(top_lines)}}],
            }
        )
    if mover_lines:
        sections.append(
            {
                "header": "増減ハイライト",
                "widgets": [{"textParagraph": {"text": "<br>".join(mover_lines)}}],
            }
        )

    return {
        "cardsV2": [
            {
                "cardId": "weekly-report",
                "card": {
                    "header": {
                        "title": "AIzen様サイト 週次レポート",
                        "subtitle": (
                            f"対象: {start.isoformat()}〜{end.isoformat()}"
                            f"（前週: {prev_start.isoformat()}〜{prev_end.isoformat()}）"
                        ),
                    },
                    "sections": sections,
                },
            }
        ]
    }
