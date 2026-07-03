"""GA4/GSCの取得結果をマージし、Google Chat向けのレポートを組み立てる。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ga4_client import GA4PageRow, GA4Totals
from gsc_client import GSCPageRow, GSCQueryRow

TOP_N = 8
MOVERS_N = 3
NEW_PAGE_THRESHOLD = 5  # 前週がこの値未満なら%表示ではなく「急伸」扱いにする
QUERY_MIN_IMPRESSIONS = 20  # これ未満の表示回数のキーワードはノイズとして無視する
STRIKING_DISTANCE_MIN_POS = 4  # この順位帯(4〜20位)は「もう一押しで上位表示」の狙い目
STRIKING_DISTANCE_MAX_POS = 20
POSITION_DROP_THRESHOLD = 2.0  # 平均順位がこれ以上悪化していたらTDH見直しを提案


@dataclass
class PageMetrics:
    path: str
    title: str
    url: str | None = None
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
        m.url = r.url
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

    # 前週の実績がほぼゼロのページは%変化が意味を持たない(1→233で+23200%等)ため、
    # 「急伸ページ」として別枠にし、既存ページの増減(movers)からは除外する。
    # ページの公開日とは無関係(古いページが急に伸びた場合もここに入る)。
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


def _keyword_movers(
    current_queries: list[GSCQueryRow], prev_queries: list[GSCQueryRow], top_n: int = MOVERS_N
):
    prev_map = {q.query: q for q in prev_queries}
    deltas = []
    for q in current_queries:
        prev = prev_map.get(q.query)
        prev_clicks = prev.clicks if prev else 0
        prev_impressions = prev.impressions if prev else 0
        if q.impressions < QUERY_MIN_IMPRESSIONS and prev_impressions < QUERY_MIN_IMPRESSIONS:
            continue
        deltas.append((q.clicks - prev_clicks, q, prev_clicks))
    deltas.sort(key=lambda x: x[0], reverse=True)
    gainers = [d for d in deltas if d[0] > 0][:top_n]
    losers = [d for d in deltas if d[0] < 0][-top_n:][::-1]
    return gainers, losers


def _find_striking_distance_keyword(current_queries: list[GSCQueryRow]) -> GSCQueryRow | None:
    """順位4〜20位・表示回数が多いキーワード = もう一押しで上位表示が狙える最大レバレッジの対象。"""
    candidates = [
        q
        for q in current_queries
        if STRIKING_DISTANCE_MIN_POS <= q.position <= STRIKING_DISTANCE_MAX_POS
        and q.impressions >= QUERY_MIN_IMPRESSIONS
    ]
    candidates.sort(key=lambda q: q.impressions, reverse=True)
    return candidates[0] if candidates else None


def _recovery_suggestion(
    page: PageMetrics,
    prev_sessions: int,
    page_queries: tuple[list[GSCQueryRow], list[GSCQueryRow]] | None,
) -> str:
    header = f"・{page.path}（{prev_sessions:,}→{page.sessions:,}セッション）"
    if not page_queries or (not page_queries[0] and not page_queries[1]):
        return f"{header}: 検索流入がほぼないページです。SNS/紹介など他の流入経路の変化を確認してください。"

    current_q, prev_q = page_queries
    prev_map = {q.query: q for q in prev_q}
    impression_drop = 0
    position_delta_sum = 0.0
    compared = 0
    for q in current_q:
        prev = prev_map.get(q.query)
        if prev is None:
            continue
        impression_drop += prev.impressions - q.impressions
        position_delta_sum += q.position - prev.position
        compared += 1
    avg_position_drop = position_delta_sum / compared if compared else 0

    if avg_position_drop > POSITION_DROP_THRESHOLD:
        return (
            f"{header}: 主要キーワードの平均順位が{avg_position_drop:.1f}位悪化しています。"
            f"タイトル・メタディスクリプション・見出し(TDH)の見直しを優先してください。"
        )
    if impression_drop > 0:
        return (
            f"{header}: 表示回数自体が落ちています（検索需要の減少、または競合の強化）。"
            f"内容を最新情報に更新するリライトを検討してください。"
        )
    return f"{header}: 検索指標に大きな変化はありません。SNS/紹介など他の流入経路の減少を確認してください。"


def build_keyword_memo(
    current_queries: list[GSCQueryRow],
    prev_queries: list[GSCQueryRow],
    top_losers: list[tuple[float, PageMetrics, int]],
    loser_page_queries: dict[str, tuple[list[GSCQueryRow], list[GSCQueryRow]]],
) -> list[str]:
    """流入キーワードの増減分析とネクストアクション提案の行リストを組み立てる。"""
    lines: list[str] = []

    gainers, losers = _keyword_movers(current_queries, prev_queries)
    if gainers:
        lines.append("<b>伸びているKW</b>")
        for delta, q, prev_clicks in gainers:
            lines.append(f"・「{q.query}」 クリック {prev_clicks:,}→{q.clicks:,} / 平均順位 {q.position:.1f}")
    if losers:
        lines.append("<b>落ちているKW</b>")
        for delta, q, prev_clicks in losers:
            lines.append(f"・「{q.query}」 クリック {prev_clicks:,}→{q.clicks:,} / 平均順位 {q.position:.1f}")

    lines.append("<b>ネクストアクション（最もレバレッジが効く一手）</b>")
    opportunity = _find_striking_distance_keyword(current_queries)
    if opportunity:
        lines.append(
            f"・「{opportunity.query}」は表示回数{opportunity.impressions:,}回・平均順位{opportunity.position:.1f}位で、"
            f"上位表示まであと一歩です。該当ページのタイトル/見出し強化や内部リンク追加で順位を押し上げれば、"
            f"表示回数はそのままクリック数を大きく伸ばせる可能性が最も高い施策です。"
        )
    elif gainers:
        lines.append(f"・「{gainers[0][1].query}」が伸びています。関連コンテンツの拡充や内部リンク強化でさらに伸ばせる余地があります。")
    else:
        lines.append("・今週は明確な伸び筋キーワードが見つかりませんでした。")

    if top_losers:
        lines.append("<b>下落ページのリカバリー提案</b>")
        for pct, cur, prev_sessions in top_losers:
            lines.append(_recovery_suggestion(cur, prev_sessions, loser_page_queries.get(cur.path)))

    return lines


def build_chat_message(report: dict, memo_lines: list[str] | None = None) -> dict:
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
        mover_lines.append("<b>急伸ページ（前週ほぼ流入なし→今週急増）</b>")
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
    if memo_lines:
        sections.append(
            {
                "header": "分析メモ",
                "widgets": [{"textParagraph": {"text": "<br>".join(memo_lines)}}],
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
