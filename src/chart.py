"""レポート用のグラフ画像を生成する。"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import japanize_matplotlib  # noqa: F401 - importするとmatplotlibの日本語フォントが自動設定される


def generate_top_pages_chart(report: dict, output_path: str, top_n: int = 8) -> None:
    """トップページのセッション数(今週 vs 前週)を横棒グラフで画像出力する。"""
    pages = report["top_pages"][:top_n]
    prev_pages = report["prev_pages"]

    labels = [p.path for p in pages][::-1]
    current_values = [p.sessions for p in pages][::-1]
    prev_values = [prev_pages.get(p.path).sessions if prev_pages.get(p.path) else 0 for p in pages][::-1]

    y = range(len(labels))
    height = 0.35

    fig, ax = plt.subplots(figsize=(9, 0.6 * len(labels) + 1.5))
    ax.barh([i + height / 2 for i in y], current_values, height=height, label="今週", color="#1a73e8")
    ax.barh([i - height / 2 for i in y], prev_values, height=height, label="前週", color="#c6d4f0")

    ax.set_yticks(list(y))
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("セッション数")
    ax.set_title("ページ別セッション数（今週 vs 前週）")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
