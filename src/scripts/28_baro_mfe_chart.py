# -*- coding: utf-8 -*-
"""28 — 바로출발(체결단계=1) 케이스에서 몇 KTR까지 가주는지 분포 차트.
v1/v2 × TF별. base종류=KTR 행만 사용."""
import csv, json, os

THRS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
TFS = ["2m", "5m", "10m"]

def load_mfe(path):
    data = {}  # tf -> list of 최대도달R_트레일1base (바로출발만)
    with open(path, encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        for r in rd:
            if r["base종류"] != "KTR": continue
            if r["체결단계"] != "1": continue  # 바로출발만
            tf = r["TF"]
            try:
                val = float(r["최대도달R_트레일1base"])
            except:
                continue
            if tf not in data: data[tf] = []
            data[tf].append(val)
    return data

base_dir = "."  # 2020_2026 디렉토리에서 실행 (다른 스크립트와 동일 규칙)
v1_path = os.path.join(base_dir, "ktr_takeprofit_N_all_tf_2010-01-01_2026-06-16.csv")
v2_path = os.path.join(base_dir, "ktr_takeprofit_N_v2_all_tf_2010-01-01_2026-06-16.csv")

v1 = load_mfe(v1_path)
v2 = load_mfe(v2_path)

def pct_reach(vals, thr):
    if not vals: return 0.0
    return 100 * sum(1 for v in vals if v >= thr) / len(vals)

# DATA[ver][tf] = {count, pcts:[...], avg, p50}
DATA = {}
for ver, dd in [("v1", v1), ("v2", v2)]:
    DATA[ver] = {}
    for tf in TFS:
        vals = dd.get(tf, [])
        n = len(vals)
        pcts = [round(pct_reach(vals, t), 1) for t in THRS]
        avg = round(sum(vals)/n, 2) if n else 0
        sv = sorted(vals)
        p50 = round(sv[n//2], 2) if n else 0
        DATA[ver][tf] = {"count": n, "pcts": pcts, "avg": avg, "p50": p50}

print("=== 바로출발 MFE 분포 ===")
for ver in ["v1", "v2"]:
    print(f"\n--- {ver} ---")
    print(f"{'TF':>5} {'건수':>6} {'평균':>6} {'중앙':>6} | " + " ".join(f"≥{t:.1f}" for t in THRS))
    for tf in TFS:
        d = DATA[ver][tf]
        row = f"{tf:>5} {d['count']:>6} {d['avg']:>6.2f} {d['p50']:>6.2f} | "
        row += " ".join(f"{p:>5.1f}%" for p in d["pcts"])
        print(row)

# HTML 생성
HTML = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>바로출발 MFE 분포</title>
<style>
body{{font-family:'Malgun Gothic',sans-serif;background:#1a1a2e;color:#e0e0e0;margin:0;padding:20px}}
h1{{color:#4fc3f7;text-align:center;font-size:1.4em}}
.subtitle{{text-align:center;color:#90a4ae;font-size:.9em;margin-bottom:20px}}
.controls{{display:flex;gap:12px;justify-content:center;margin-bottom:24px;flex-wrap:wrap}}
.btn{{padding:8px 16px;border:2px solid #4fc3f7;background:transparent;color:#4fc3f7;
      border-radius:6px;cursor:pointer;font-size:.85em;transition:all .2s}}
.btn.active{{background:#4fc3f7;color:#1a1a2e;font-weight:bold}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:20px}}
.card{{background:#16213e;border-radius:10px;padding:20px;border:1px solid #2a4a7f}}
.card-title{{color:#4fc3f7;font-size:1em;margin-bottom:4px}}
.card-meta{{color:#90a4ae;font-size:.8em;margin-bottom:16px}}
.bar-row{{display:flex;align-items:center;margin-bottom:8px;gap:8px}}
.bar-label{{width:55px;text-align:right;font-size:.85em;color:#b0bec5}}
.bar-wrap{{flex:1;background:#0d1b2a;border-radius:4px;height:22px;position:relative}}
.bar{{height:100%;border-radius:4px;transition:width .5s ease;min-width:2px}}
.bar-val{{position:absolute;right:6px;top:50%;transform:translateY(-50%);
           font-size:.82em;color:#fff;font-weight:bold}}
.stats{{margin-top:12px;display:flex;gap:16px;font-size:.82em;color:#90a4ae}}
.stat-v{{color:#e0e0e0;font-weight:bold}}
</style>
</head>
<body>
<h1>바로출발 케이스 — 몇 KTR까지 가주는지</h1>
<div class="subtitle">체결단계=1 (최초 돌파가에서만 진입, 추가 눌림 없음) · KTR base 기준</div>
<div class="controls">
  <span style="color:#90a4ae;align-self:center">버전:</span>
  <button class="btn active" onclick="setVer('v1')">v1 (즉시진입)</button>
  <button class="btn" onclick="setVer('v2')">v2 (풀백진입)</button>
</div>
<div class="grid" id="grid"></div>

<script>
const THRS = {json.dumps(THRS)};
const DATA = {json.dumps(DATA)};
const COLORS = ['#ef5350','#ff7043','#ffa726','#ffee58','#66bb6a','#26c6da','#42a5f5','#ab47bc'];
let curVer = 'v1';

function pctColor(p) {{
  if(p>=80) return '#66bb6a';
  if(p>=60) return '#26c6da';
  if(p>=40) return '#42a5f5';
  if(p>=20) return '#ffa726';
  return '#ef5350';
}}

function render() {{
  const grid = document.getElementById('grid');
  grid.innerHTML = '';
  const tfs = ['2m','5m','10m'];
  tfs.forEach(tf => {{
    const d = DATA[curVer][tf];
    const card = document.createElement('div');
    card.className = 'card';
    let bars = '';
    THRS.forEach((t, i) => {{
      const p = d.pcts[i];
      const col = pctColor(p);
      bars += `<div class="bar-row">
        <div class="bar-label">≥${{t.toFixed(1)}} KTR</div>
        <div class="bar-wrap">
          <div class="bar" style="width:${{p}}%;background:${{col}}"></div>
          <div class="bar-val">${{p.toFixed(1)}}%</div>
        </div>
      </div>`;
    }});
    card.innerHTML = `
      <div class="card-title">${{tf}} — 바로출발 MFE 분포</div>
      <div class="card-meta">바로출발 ${{d.count.toLocaleString()}}건 (${{curVer}})</div>
      ${{bars}}
      <div class="stats">
        <span>평균 <span class="stat-v">${{d.avg.toFixed(2)}} KTR</span></span>
        <span>중앙값 <span class="stat-v">${{d.p50.toFixed(2)}} KTR</span></span>
      </div>`;
    grid.appendChild(card);
  }});
}}

function setVer(v) {{
  curVer = v;
  document.querySelectorAll('.btn').forEach(b => b.classList.toggle('active', b.textContent.startsWith(v)));
  render();
}}

render();
</script>
</body>
</html>"""

out_path = os.path.join("..", "result", "baro_mfe_chart.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(HTML)
print(f"\n→ {out_path}")
