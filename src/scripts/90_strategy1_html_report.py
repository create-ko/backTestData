# -*- coding: utf-8 -*-
"""Build an HTML report for Strategy 1 avg+5P close-trailing results."""
from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = ROOT / "result" / "strategy1_h1_breakout_120sma_ktr_grid_cost05_entry0830_2330_no_time_exit"
OUT_HTML = RESULT_DIR / "strategy1_120sma_avg5p_trail_report.html"

PREFIX = "strategy1_120sma_3scale_10p_stop5p_close_trail"


def read_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(RESULT_DIR / f"{PREFIX}_{name}.csv")


def fmt_value(value, col: str) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        if col.endswith("_rate") or col == "win_rate":
            return f"{value * 100:.1f}%"
        return f"{value:,.3f}"
    return escape(str(value))


def table_html(df: pd.DataFrame, title: str, subtitle: str = "", max_rows: int | None = None) -> str:
    shown = df.head(max_rows).copy() if max_rows else df.copy()
    headers = "".join(f"<th>{escape(str(c))}</th>" for c in shown.columns)
    rows = []
    for _, row in shown.iterrows():
        cells = []
        for col, value in row.items():
            klass = ""
            if col in {"expectancy_10p", "expectancy_points_total", "cumulative_points", "profit_factor"}:
                try:
                    num = float(value)
                    if col == "profit_factor":
                        klass = "pos" if num >= 1 else "neg"
                    else:
                        klass = "pos" if num > 0 else "neg" if num < 0 else ""
                except (TypeError, ValueError):
                    klass = ""
            cells.append(f"<td class=\"{klass}\">{fmt_value(value, col)}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    note = f"<p class=\"subtle\">{escape(subtitle)}</p>" if subtitle else ""
    return f"""
    <section>
      <h2>{escape(title)}</h2>
      {note}
      <div class="table-wrap">
        <table>
          <thead><tr>{headers}</tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </section>
    """


def metric_card(label: str, value: str, detail: str = "", tone: str = "") -> str:
    return f"""
    <div class="card {tone}">
      <div class="label">{escape(label)}</div>
      <div class="value">{escape(value)}</div>
      <div class="detail">{escape(detail)}</div>
    </div>
    """


def make_html() -> str:
    summary = read_csv("summary")
    by_session = read_csv("by_session")
    by_year = read_csv("by_year")
    by_exit = read_csv("by_exit")
    by_fills = read_csv("by_fills")

    summary_sorted = summary.sort_values("expectancy_10p", ascending=False)
    session_sorted = by_session.sort_values("expectancy_10p", ascending=False)
    fills_sorted = by_fills.sort_values(["entry_tf", "direction", "filled_entries"])
    exit_sorted = by_exit.sort_values(["entry_tf", "direction", "exit_reason"])

    long_only = summary[summary["direction"] == "long"].sort_values("expectancy_10p", ascending=False)
    short_only = summary[summary["direction"] == "short"].sort_values("expectancy_10p", ascending=False)
    best = summary_sorted.iloc[0]
    best_long = long_only.iloc[0]
    best_short = short_only.iloc[0]

    positive = summary_sorted[summary_sorted["expectancy_10p"] > 0]
    positive_label = ", ".join(
        f"{r.entry_tf} {r.direction}" for _, r in positive.iterrows()
    ) or "none"

    cards = "".join([
        metric_card(
            "Best config",
            f"{best['entry_tf']} {best['direction']}",
            f"expectancy {best['expectancy_10p']:.3f} per 10P, PF {best['profit_factor']:.3f}",
            "pos" if best["expectancy_10p"] > 0 else "neg",
        ),
        metric_card(
            "Positive configs",
            positive_label,
            "Only these combinations stayed positive after cost.",
            "pos" if len(positive) else "neg",
        ),
        metric_card(
            "Best long",
            f"{best_long['entry_tf']} long",
            f"win {best_long['win_rate']*100:.1f}%, cum {best_long['cumulative_points']:.1f}P",
            "pos" if best_long["expectancy_10p"] > 0 else "neg",
        ),
        metric_card(
            "Best short",
            f"{best_short['entry_tf']} short",
            f"expectancy {best_short['expectancy_10p']:.3f}, PF {best_short['profit_factor']:.3f}",
            "pos" if best_short["expectancy_10p"] > 0 else "neg",
        ),
    ])

    key_notes = """
    <section class="notes">
      <h2>판정</h2>
      <ul>
        <li><strong>롱 중심 후보</strong>: 비용 0.5P와 KST 08:30~23:30 진입 필터 적용 후 fixed_10p 롱 조합은 모두 양수입니다.</li>
        <li><strong>KTR 그리드 효과</strong>: session_ktr는 1m long만 거의 본전 수준으로 살아있고, 전체적으로 fixed_10p가 더 강합니다.</li>
        <li><strong>숏은 제외 또는 별도 필터 필요</strong>: 모든 숏 조합이 음수 기대값입니다.</li>
        <li><strong>5m/10m은 약함</strong>: 비용 0.5P 기준에서는 5m/10m 롱도 뚜렷한 우위가 없습니다.</li>
        <li><strong>시간청산 없음</strong>: 진입 후에는 손절 또는 트레일링 청산까지 보유합니다. 데이터 종료까지 미청산인 경우만 별도 표시합니다.</li>
      </ul>
    </section>
    """

    rules = """
    <section class="rules">
      <h2>테스트 기준</h2>
      <div class="rule-grid">
        <div><b>Setup</b><span>1H double-BB breakout</span></div>
        <div><b>Entry</b><span>first 120SMA touch on 1m/2m/5m/10m</span></div>
        <div><b>Scale</b><span>fixed_10p and session_ktr compared</span></div>
        <div><b>Hard stop</b><span>3rd entry +/- 5P</span></div>
        <div><b>Profit exit</b><span>close recovers avg +/- 5P, then close-based 5P trailing</span></div>
        <div><b>Cost</b><span>0.50P per filled unit round turn</span></div>
        <div><b>Time exit</b><span>none after entry</span></div>
        <div><b>Entry time</b><span>KST 08:30 to 23:30 only</span></div>
      </div>
    </section>
    """

    sections = [
        table_html(
            summary_sorted,
            "전체 요약",
            "expectancy_10p 기준 내림차순. 양수는 초록, 음수는 빨강.",
        ),
        table_html(
            session_sorted,
            "세션별 상위 결과",
            "세션 필터 후보를 보기 위한 표입니다.",
            max_rows=32,
        ),
        table_html(
            fills_sorted,
            "체결 수별 결과",
            "3차 체결이 전체 기대값을 얼마나 훼손하는지 확인하는 표입니다.",
        ),
        table_html(
            exit_sorted,
            "청산 사유별 결과",
            "close_trail_5p, hard_stop, time_exit 별 손익 구조입니다.",
        ),
        table_html(
            by_year.sort_values(["entry_tf", "direction", "year"]),
            "연도별 결과",
            "연도 안정성 확인용입니다.",
        ),
    ]

    css = """
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #17202a;
      --muted: #687386;
      --line: #d9dee7;
      --pos: #087f5b;
      --pos-bg: #e6f4ee;
      --neg: #c92a2a;
      --neg-bg: #fff0f0;
      --accent: #1c5d99;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Arial, "Malgun Gothic", sans-serif;
      background: var(--bg);
      color: var(--ink);
      line-height: 1.5;
    }
    header {
      padding: 34px 42px 24px;
      background: #101820;
      color: white;
    }
    header h1 { margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }
    header p { margin: 0; color: #c9d3df; }
    main { padding: 24px 42px 52px; max-width: 1680px; margin: 0 auto; }
    .cards {
      display: grid;
      grid-template-columns: repeat(4, minmax(180px, 1fr));
      gap: 14px;
      margin-bottom: 18px;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      min-height: 112px;
    }
    .card.pos { border-left: 5px solid var(--pos); }
    .card.neg { border-left: 5px solid var(--neg); }
    .label { color: var(--muted); font-size: 13px; }
    .value { font-size: 22px; font-weight: 700; margin: 8px 0; }
    .detail { color: var(--muted); font-size: 13px; }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px;
      margin: 16px 0;
    }
    h2 { margin: 0 0 10px; font-size: 19px; }
    .subtle { color: var(--muted); margin: -4px 0 14px; }
    .notes ul { margin: 8px 0 0 20px; padding: 0; }
    .notes li { margin: 6px 0; }
    .rule-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(220px, 1fr));
      gap: 10px;
    }
    .rule-grid div {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fbfcfe;
    }
    .rule-grid b { display: block; margin-bottom: 4px; color: var(--accent); }
    .rule-grid span { color: var(--muted); }
    .table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; background: white; }
    th, td { padding: 8px 10px; border-bottom: 1px solid var(--line); text-align: right; white-space: nowrap; }
    th { position: sticky; top: 0; background: #eef2f7; color: #263241; z-index: 1; }
    td:first-child, th:first-child,
    td:nth-child(2), th:nth-child(2),
    td:nth-child(3), th:nth-child(3) { text-align: left; }
    tr:hover td { background: #f8fafc; }
    td.pos { color: var(--pos); font-weight: 700; background: var(--pos-bg); }
    td.neg { color: var(--neg); font-weight: 700; background: var(--neg-bg); }
    footer { color: var(--muted); font-size: 12px; padding: 10px 42px 28px; }
    @media (max-width: 1000px) {
      header, main, footer { padding-left: 18px; padding-right: 18px; }
      .cards { grid-template-columns: repeat(2, minmax(160px, 1fr)); }
      .rule-grid { grid-template-columns: 1fr; }
    }
    """

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Strategy 1 120SMA Avg+5P Trail Report</title>
  <style>{css}</style>
</head>
<body>
  <header>
    <h1>Strategy 1: 1H Double-BB -> 120SMA Retest</h1>
    <p>3-scale 10P entries, hard stop at third entry +/- 5P, avg +/- 5P close recovery then 5P close trailing</p>
  </header>
  <main>
    <div class="cards">{cards}</div>
    {key_notes}
    {rules}
    {''.join(sections)}
  </main>
  <footer>
    Source: {escape(str(RESULT_DIR))}<br>
    Generated from CSV result files. Values are rounded for display.
  </footer>
</body>
</html>
"""


def main() -> None:
    html = make_html()
    OUT_HTML.write_text(html, encoding="utf-8")
    print("WROTE:", OUT_HTML)


if __name__ == "__main__":
    main()
