# -*- coding: utf-8 -*-
"""Build yearly stability report for Strategy 1 latest run."""
from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = ROOT / "result" / "strategy1_h1_breakout_120sma_ktr_grid_cost05_entry0830_2330_no_time_exit"
PREFIX = "strategy1_120sma_3scale_10p_stop5p_close_trail"
OUT_HTML = RESULT_DIR / "strategy1_yearly_stability_report.html"
OUT_CSV = RESULT_DIR / "strategy1_yearly_stability_core.csv"


CORE_COLS = [
    "grid_method",
    "entry_tf",
    "direction",
    "year",
    "trades",
    "expectancy_10p",
    "profit_factor",
    "cumulative_points",
    "max_drawdown_points",
    "win_rate",
]


def fmt(v, col: str) -> str:
    if pd.isna(v):
        return ""
    if col == "win_rate":
        return f"{float(v) * 100:.1f}%"
    if col in {"expectancy_10p", "profit_factor", "cumulative_points", "max_drawdown_points"}:
        try:
            return f"{float(v):,.3f}"
        except ValueError:
            return escape(str(v))
    return escape(str(v))


def table_html(df: pd.DataFrame, title: str, note: str = "") -> str:
    headers = "".join(f"<th>{escape(c)}</th>" for c in df.columns)
    rows = []
    for _, row in df.iterrows():
        cells = []
        for col, value in row.items():
            klass = ""
            if col in {"expectancy_10p", "cumulative_points"}:
                num = float(value)
                klass = "pos" if num > 0 else "neg" if num < 0 else ""
            if col == "profit_factor":
                try:
                    num = float(value)
                    klass = "pos" if num >= 1 else "neg"
                except ValueError:
                    klass = "pos"
            cells.append(f"<td class=\"{klass}\">{fmt(value, col)}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    note_html = f"<p>{escape(note)}</p>" if note else ""
    return f"""
    <section>
      <h2>{escape(title)}</h2>
      {note_html}
      <div class="table-wrap">
        <table>
          <thead><tr>{headers}</tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </section>
    """


def make_tf_pivot(core: pd.DataFrame, grid_method: str) -> pd.DataFrame:
    data = core[(core["grid_method"] == grid_method) & (core["direction"] == "long")].copy()
    rows = []
    for year, group in data.groupby("year", sort=True):
        row = {"year": int(year)}
        for tf in ["1m", "2m", "5m", "10m"]:
            item = group[group["entry_tf"] == tf]
            if item.empty:
                row[f"{tf}_trades"] = ""
                row[f"{tf}_exp"] = ""
                row[f"{tf}_pf"] = ""
                row[f"{tf}_pnl"] = ""
                row[f"{tf}_mdd"] = ""
            else:
                r = item.iloc[0]
                row[f"{tf}_trades"] = int(r["trades"])
                row[f"{tf}_exp"] = round(float(r["expectancy_10p"]), 3)
                row[f"{tf}_pf"] = round(float(r["profit_factor"]), 3) if str(r["profit_factor"]) != "inf" else "inf"
                row[f"{tf}_pnl"] = round(float(r["cumulative_points"]), 3)
                row[f"{tf}_mdd"] = round(float(r["max_drawdown_points"]), 3)
        rows.append(row)
    return pd.DataFrame(rows)


def make_html(core: pd.DataFrame) -> str:
    fixed_long = core[(core["grid_method"] == "fixed_10p") & (core["direction"] == "long")].copy()
    ktr_long = core[(core["grid_method"] == "session_ktr") & (core["direction"] == "long")].copy()
    fixed_pivot = make_tf_pivot(core, "fixed_10p")
    ktr_pivot = make_tf_pivot(core, "session_ktr")

    css = """
    body { margin: 0; font-family: Arial, "Malgun Gothic", sans-serif; background: #f6f7f9; color: #17202a; }
    header { padding: 30px 42px; background: #101820; color: white; }
    h1 { margin: 0 0 8px; font-size: 26px; }
    header p { margin: 0; color: #c9d3df; }
    main { padding: 24px 42px 48px; max-width: 1800px; margin: 0 auto; }
    section { background: white; border: 1px solid #d9dee7; border-radius: 8px; padding: 18px; margin: 16px 0; }
    h2 { margin: 0 0 8px; font-size: 18px; }
    p { margin: 0 0 12px; color: #687386; }
    .table-wrap { overflow-x: auto; border: 1px solid #d9dee7; border-radius: 8px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; background: white; }
    th, td { border-bottom: 1px solid #d9dee7; padding: 7px 9px; text-align: right; white-space: nowrap; }
    th { background: #eef2f7; color: #263241; position: sticky; top: 0; }
    td:first-child, th:first-child, td:nth-child(2), th:nth-child(2), td:nth-child(3), th:nth-child(3) { text-align: left; }
    .pos { color: #087f5b; font-weight: 700; background: #e6f4ee; }
    .neg { color: #c92a2a; font-weight: 700; background: #fff0f0; }
    """
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Strategy 1 Yearly Stability</title>
  <style>{css}</style>
</head>
<body>
  <header>
    <h1>Strategy 1 Yearly Stability</h1>
    <p>Cost 0.5P, KST entry 08:30-23:30, no time exit, avg +/-5P close trailing</p>
  </header>
  <main>
    {table_html(fixed_pivot, "Fixed 10P Long - 연도별 TF 비교", "각 연도별 거래수 / 기대값 / PF / 누적손익 / 최대DD를 TF별로 나란히 봅니다.")}
    {table_html(fixed_long[CORE_COLS], "Fixed 10P Long - 상세 연도별")}
    {table_html(ktr_pivot, "Session KTR Long - 연도별 TF 비교")}
    {table_html(ktr_long[CORE_COLS], "Session KTR Long - 상세 연도별")}
  </main>
</body>
</html>
"""


def main() -> None:
    yearly = pd.read_csv(RESULT_DIR / f"{PREFIX}_by_year.csv")
    core = yearly[CORE_COLS].copy()
    core = core.sort_values(["grid_method", "entry_tf", "direction", "year"])
    core.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    OUT_HTML.write_text(make_html(core), encoding="utf-8")
    print("WROTE:", OUT_CSV)
    print("WROTE:", OUT_HTML)


if __name__ == "__main__":
    main()
