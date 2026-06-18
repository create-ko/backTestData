// run_fetch.mjs  [instrumentFilter]
// ============================================================
// 전체 수집 오케스트레이터: eurusd/gbpusd/usdjpy(2010~2026-06-16) + xauusd(2010~2019).
// fetch_inst.mjs를 인스트루먼트×연도 슬라이스로 병렬 실행(동시 5) → parts → 병합 → 검증.
// 출력: ../{inst}_{tf}_{start}_{end}.csv (BOM+헤더, time=epoch초, MID).
// 재개 가능: 이미 받은 연도(parts/{label}_1m.csv 존재&비어있지않음)는 건너뜀.
// 사용:  node run_fetch.mjs           (전체)
//        node run_fetch.mjs eurusd    (한 인스트루먼트만)
// ============================================================
import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';

const CONCURRENCY = 5;
const PARTS = path.resolve('parts');
const OUT_DIR = path.resolve('..');
const TFS = ['1m', '2m', '5m', '10m'];
fs.mkdirSync(PARTS, { recursive: true });

// 인스트루먼트별: short, instrument, 시작연, 종료(배타) ISO, 파일명용 start/end
const JOBS = [
  { short: 'eur', inst: 'eurusd', y0: 2010, endISO: '2026-06-16', fname: ['2010-01-01', '2026-06-16'] },
  { short: 'gbp', inst: 'gbpusd', y0: 2010, endISO: '2026-06-16', fname: ['2010-01-01', '2026-06-16'] },
  { short: 'jpy', inst: 'usdjpy', y0: 2010, endISO: '2026-06-16', fname: ['2010-01-01', '2026-06-16'] },
  { short: 'xau', inst: 'xauusd', y0: 2010, endISO: '2020-01-01', fname: ['2010-01-01', '2019-12-31'] },
];

const filter = process.argv[2];
const jobs = filter ? JOBS.filter(j => j.inst === filter || j.short === filter) : JOBS;
if (jobs.length === 0) { console.error('해당 인스트루먼트 없음:', filter); process.exit(1); }

// 연도 슬라이스 생성 (label, from, to)
function slices(job) {
  const out = [];
  const endY = parseInt(job.endISO.slice(0, 4), 10);
  for (let y = job.y0; y <= endY; y++) {
    const from = `${y}-01-01`;
    let to = `${y + 1}-01-01`;
    if (to > job.endISO) to = job.endISO;        // 마지막 슬라이스는 종료ISO까지
    if (from >= job.endISO) break;
    out.push({ label: `${job.short}_${y}`, from, to });
  }
  return out;
}
function done(label) {
  const fp = path.join(PARTS, `${label}_1m.csv`);
  try { return fs.statSync(fp).size > 0; } catch { return false; }
}
function runOne(job, sl) {
  return new Promise((resolve) => {
    if (done(sl.label)) { console.log(`[skip] ${sl.label} (이미 있음)`); return resolve(); }
    const args = ['fetch_inst.mjs', sl.from, sl.to, sl.label, job.inst, job.fname[0],
      job.short === 'xau' ? '2020-01-01' : '2026-06-16'];
    console.log(`[start] ${sl.label}  (${sl.from}~${sl.to})`);
    const p = spawn('node', args, { stdio: ['ignore', 'inherit', 'inherit'] });
    p.on('close', (code) => { console.log(`[end]   ${sl.label} exit=${code}`); resolve(); });
  });
}
async function pool(tasks, n) {
  let i = 0;
  async function worker() {
    while (i < tasks.length) {
      const idx = i++;
      await tasks[idx]();
    }
  }
  await Promise.all(Array.from({ length: Math.min(n, tasks.length) }, worker));
}

// ---------- 1) 수집 ----------
const allTasks = [];
for (const job of jobs) for (const sl of slices(job)) allTasks.push(() => runOne(job, sl));
console.log(`총 ${allTasks.length}개 연도-슬라이스, 동시 ${CONCURRENCY}\n`);
await pool(allTasks, CONCURRENCY);

// ---------- 2) 병합 + 검증 ----------
const KST = 9 * 3600;
const kstStr = (s) => new Date((s + KST) * 1000).toISOString().replace('T', ' ').slice(0, 16);
const kstMonth = (s) => { const d = new Date((s + KST) * 1000); return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`; };

console.log('\n========== 병합 + 검증 ==========');
for (const job of jobs) {
  const labels = slices(job).map(s => s.label);
  for (const tf of TFS) {
    let body = '';
    for (const lb of labels) {
      const fp = path.join(PARTS, `${lb}_${tf}.csv`);
      if (fs.existsSync(fp)) body += fs.readFileSync(fp, 'utf8');
    }
    const out = path.join(OUT_DIR, `${job.inst}_${tf}_${job.fname[0]}_${job.fname[1]}.csv`);
    fs.writeFileSync(out, '﻿' + 'time,open,high,low,close,volume\n' + body, 'utf8');
    const lines = body.split('\n').filter(Boolean);
    if (tf === '2m') {
      const times = lines.map(l => parseInt(l.split(',')[0], 10)).sort((a, b) => a - b);
      let dup = 0, back = 0;
      for (let i = 1; i < times.length; i++) { if (times[i] === times[i - 1]) dup++; if (times[i] < times[i - 1]) back++; }
      const byM = {}; for (const t of times) byM[kstMonth(t)] = (byM[kstMonth(t)] || 0) + 1;
      const low = Object.entries(byM).filter(([, c]) => c < 3000).map(([m, c]) => `${m}:${c}`);
      console.log(`\n[${job.inst}] 2m ${times.length}행 | ${kstStr(times[0])}~${kstStr(times[times.length - 1])} | 중복${dup} 역순${back}`);
      console.log(`  ⚠ 저봉수월(3000미만): ${low.length ? low.join(', ') : '없음'}`);
    } else {
      console.log(`[${job.inst}] ${tf} ${lines.length}행 -> ${path.basename(out)}`);
    }
  }
}
console.log('\n완료. 산출물은 D:\\claude\\2020_2026 에 {inst}_{tf}_{start}_{end}.csv');
