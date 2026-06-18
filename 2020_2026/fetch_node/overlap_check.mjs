// 새 2m(2020~2026) vs 기존 2m(2025~2026) 겹침 구간 정합성 대조
import fs from 'fs';
import path from 'path';
const OUT = path.resolve('..');

function load(fp) {
  const lines = fs.readFileSync(fp, 'utf8').replace(/^﻿/, '').split('\n').filter(Boolean);
  const m = new Map();
  for (let i = 1; i < lines.length; i++) {
    const c = lines[i].split(',');
    m.set(Math.round(parseFloat(c[0])), parseFloat(c[4])); // time -> close
  }
  return m;
}
const neu = load(path.join(OUT, 'xauusd_2m_2020-01-01_2026-06-16.csv'));
const old = load(path.join(OUT, 'xauusd_2m_2025-01-01_2026-06-16.csv'));

let n = 0, sumAbs = 0, maxAbs = 0, missing = 0;
for (const [t, oc] of old) {
  const nc = neu.get(t);
  if (nc === undefined) { missing++; continue; }
  const d = Math.abs(nc - oc);
  n++; sumAbs += d; if (d > maxAbs) maxAbs = d;
}
console.log(`기존 2m 봉수: ${old.size}`);
console.log(`매칭된 봉: ${n}`);
console.log(`새 데이터에 없는 기존 timestamp: ${missing}`);
console.log(`종가 평균 절대차: ${(sumAbs / n).toFixed(4)}`);
console.log(`종가 최대 절대차: ${maxAbs.toFixed(4)}`);
