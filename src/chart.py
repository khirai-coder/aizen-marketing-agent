"""レポート用のグラフ画像を生成する。"""
from __future__ import annotations

import glob

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

from ga4_client import GA4MonthlyRow

# CI環境(Ubuntu)にはデフォルトで日本語フォントが入っていないため、
# ワークフロー側でfonts-noto-cjkを事前インストールし、ここで実ファイルを探して登録する。
# (japanize-matplotlib等のラッパーはdistutils依存でPython3.12では動かないため使わない)
_CJK_CANDIDATES = sorted(
    glob.glob("/usr/share/fonts/**/NotoSansCJK*.ttc", recursive=True)
    + glob.glob("/usr/share/fonts/**/NotoSansCJK*.otf", recursive=True)
)
if _CJK_CANDIDATES:
    fm.fontManager.addfont(_CJK_CANDIDATES[0])
    plt.rcParams["font.family"] = fm.FontProperties(fname=_CJK_CANDIDATES[0]).get_name()


def generate_monthly_organic_chart(monthly_rows: list[GA4MonthlyRow], output_path: str) -> None:
    """オーガニック月次セッション数(棒/左軸)とCV数(折れ線/右軸)を描画する。"""
    labels = [f"{r.year_month[:4]}/{r.year_month[4:]}" for r in monthly_rows]
    sessions = [r.sessions for r in monthly_rows]
    conversions = [r.conversions for r in monthly_rows]

    fig, ax1 = plt.subplots(figsize=(9, 4.5))
    ax1.bar(labels, sessions, color="#1a73e8", label="オーガニックセッション数")
    ax1.set_ylabel("セッション数")
    ax1.tick_params(axis="x", rotation=45)

    ax2 = ax1.twinx()
    ax2.plot(labels, conversions, color="#ea4335", marker="o", linewidth=2, label="コンバージョン数")
    ax2.set_ylabel("コンバージョン数")
    ax2.set_ylim(bottom=0)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

    ax1.set_title("オーガニック月次セッション数とコンバージョン数の推移")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
