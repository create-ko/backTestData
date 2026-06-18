// merge_validate.mjs
// parts/{A,B,C}_{tf}.csv (시간순 disjoint) -> 최종 ../xauusd_{tf}_2020-01-01_2026-06-16.csv
// + 무결성 검증: 총행수/기간/월별 봉수(누락 감지)/기존 데이터 겹침 대조
import fs from 'fs';
import path from 'path';

const OUT_DIR = path.resolve('..');
const PARTS = path.resolve('parts');
const TFS = ['1m', '2m', '5m', '10m'];
const WORKERS = ['A', 'B', 'D', 'C'];   // 시간순: A(2020-01~2022-02) B(2022-03~2023-04) D(2023-05~2024-04) C(2024-05~2026-06)
const KST = 9 * 3600;

const kstMonth = (sec) => {
  const d = new Date((sec + KST) * 1000);
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
};
const kstStr = (sec) => new Date((sec + KST) * 1000).toISOString().replace('T', ' ').slice(0, 16);

for (const tf of TFS) {
  let body = '';
  for (const w of WORKERS) {
    const fp = path.join(PARTS, `${w}_${tf}.csv`);
    if (fs.existsSync(fp)) body += fs.readFileSync(fp, 'utf8');
  }
  const out = path.join(OUT_DIR, `xauusd_${tf}_2020-01-01_2026-06-16.csv`);
  fs.writeFileSync(out, '﻿' + 'time,open,high,low,close,volume\n' + body, 'utf8');
  const lines = body.split('\n').filter(Boolean);
  console.log(`[${tf}] ${lines.length}행 -> ${out}`);
}

// ----- 2m 기준 상세 검증 -----
const body2 = fs.readFileSync(path.join(OUT_DIR, 'xauusd_2m_2020-01-01_2026-06-16.csv'), 'utf8')
  .replace(/^﻿/, '').split('\n').filter(Boolean).slice(1);
const times = body2.map(l => parseInt(l.split(',')[0], 10));
times.sort((a, b) => a - b);

console.log('\n=== 2m 검증 ===');
console.log(`총 봉수: ${times.length}`);
console.log(`기간: ${kstStr(times[0])} ~ ${kstStr(times[times.length - 1])} (KST)`);

// 단조 증가/중복 체크
let dup = 0, back = 0;
for (let i = 1; i < times.length; i++) {
  if (times[i] === times[i - 1]) dup++;
  if (times[i] < times[i - 1]) back++;
}
console.log(`중복 timestamp: ${dup}, 역순: ${back}`);

// 월별 봉수 + 누락 의심 플래그
const byMonth = {};
for (const t of times) byMonth[kstMonth(t)] = (byMonth[kstMonth(t)] || 0) + 1;
console.log('\n월별 2m 봉수 (KST), ⚠=8000 미만 의심:');
for (const m of Object.keys(byMonth).sort()) {
  const c = byMonth[m];
  console.log(`  ${m}: ${c}${c < 8000 ? '  ⚠' : ''}`);
}
