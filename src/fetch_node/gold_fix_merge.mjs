// gold_fix_merge.mjs
// 골드 2010-2019 파일에 재페치 파트(xaufix_hole, xaufix_tail)를 병합.
// 정책: 기존(검증된) 행은 유지, 누락 timestamp만 추가(union). 원본은 .bak 백업.
// 출력: ../../data/xauusd_{tf}_2010-01-01_2019-12-31.csv (BOM+헤더, ts오름차순)
import fs from 'node:fs';
import path from 'node:path';

const DATA = path.resolve('..', '..', 'data');
const PARTS = path.resolve('parts');
const TFS = ['1m', '2m', '5m', '10m'];
const FIX_LABELS = ['xaufix_hole', 'xaufix_tail'];

function readCsvMap(fp, map) {
  if (!fs.existsSync(fp)) return 0;
  const txt = fs.readFileSync(fp, 'utf8').replace(/^﻿/, '');
  let added = 0;
  for (const raw of txt.split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('time,')) continue;
    const comma = line.indexOf(',');
    if (comma <= 0) continue;
    const ts = Number(line.slice(0, comma));
    if (!Number.isFinite(ts)) continue;
    if (!map.has(ts)) { map.set(ts, line); added++; }   // 기존 우선: 이미 있으면 건드리지 않음
  }
  return added;
}

for (const tf of TFS) {
  const target = path.join(DATA, `xauusd_${tf}_2010-01-01_2019-12-31.csv`);
  const map = new Map();
  // 1) 기존 데이터 먼저 적재(우선권)
  const existing = readCsvMap(target, map);
  const before = map.size;
  // 2) 재페치 파트 병합(누락분만)
  let addedHole = 0, addedTail = 0;
  addedHole += readCsvMap(path.join(PARTS, `xaufix_hole_${tf}.csv`), map);
  addedTail += readCsvMap(path.join(PARTS, `xaufix_tail_${tf}.csv`), map);
  const after = map.size;

  // 3) 정렬 + 쓰기 (백업 후)
  const rows = [...map.entries()].sort((a, b) => a[0] - b[0]).map(e => e[1]);
  if (fs.existsSync(target)) fs.copyFileSync(target, target + '.bak');
  fs.writeFileSync(target, '﻿time,open,high,low,close,volume\n' + rows.join('\n') + '\n', 'utf8');

  const kst = (s) => new Date((s + 9 * 3600) * 1000).toISOString().replace('T', ' ').slice(0, 16);
  const ts = rows.map(l => Number(l.slice(0, l.indexOf(','))));
  console.log(`[${tf}] 기존 ${before} (+구멍 ${addedHole}, +꼬리 ${addedTail}) = ${after}행`);
  console.log(`     기간 ${kst(ts[0])} ~ ${kst(ts[ts.length - 1])} (KST)  백업: ${path.basename(target)}.bak`);
}
console.log('병합 완료.');
