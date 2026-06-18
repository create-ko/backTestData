// fix_merge.mjs <targetPattern> <labelsCsv> [tfCsv]
// 재페치 파트(parts/{label}_{tf}.csv)를 기존 합본 CSV(../../data/)에 union 병합.
// 정책: 기존(검증된) 행 유지, 누락 timestamp만 추가. 원본은 .bak 백업.
//
// 예: node fix_merge.mjs "usdjpy_{tf}_2010-01-01_2026-06-16.csv" jpyfix_2011,jpyfix_2014
import fs from 'node:fs';
import path from 'node:path';

const [, , targetPattern, labelsArg, tfArg = '1m,2m,5m,10m'] = process.argv;
if (!targetPattern || !labelsArg) {
  console.error('usage: node fix_merge.mjs <targetPattern{tf}> <labelsCsv> [tfCsv]');
  process.exit(1);
}
const DATA = path.resolve('..', '..', 'data');
const PARTS = path.resolve('parts');
const TFS = tfArg.split(',').map(s => s.trim()).filter(Boolean);
const LABELS = labelsArg.split(',').map(s => s.trim()).filter(Boolean);
const kst = (s) => new Date((s + 9 * 3600) * 1000).toISOString().replace('T', ' ').slice(0, 16);

function readInto(fp, map) {
  if (!fs.existsSync(fp)) return 0;
  const txt = fs.readFileSync(fp, 'utf8').replace(/^﻿/, '');
  let added = 0;
  for (const raw of txt.split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('time,')) continue;
    const c = line.indexOf(',');
    if (c <= 0) continue;
    const ts = Number(line.slice(0, c));
    if (!Number.isFinite(ts)) continue;
    if (!map.has(ts)) { map.set(ts, line); added++; }   // 기존 우선
  }
  return added;
}

for (const tf of TFS) {
  const target = path.join(DATA, targetPattern.replaceAll('{tf}', tf));
  const map = new Map();
  const existing = readInto(target, map);          // 기존 합본 먼저(우선권)
  let addedFix = 0;
  const perLabel = [];
  for (const lb of LABELS) {
    const a = readInto(path.join(PARTS, `${lb}_${tf}.csv`), map);
    addedFix += a; perLabel.push(`${lb}+${a}`);
  }
  const rows = [...map.entries()].sort((a, b) => a[0] - b[0]).map(e => e[1]);
  if (fs.existsSync(target)) fs.copyFileSync(target, target + '.bak');
  fs.writeFileSync(target, '﻿time,open,high,low,close,volume\n' + rows.join('\n') + '\n', 'utf8');
  const ts = rows.map(l => Number(l.slice(0, l.indexOf(','))));
  console.log(`[${tf}] 기존 ${existing} (+${perLabel.join(' ')}) = ${rows.length}행`);
  console.log(`     기간 ${kst(ts[0])} ~ ${kst(ts[ts.length - 1])}  백업: ${path.basename(target)}.bak`);
}
console.log('병합 완료.');
