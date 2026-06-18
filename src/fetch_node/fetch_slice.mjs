// fetch_slice.mjs <fromISO> <toISO> <label>
// ============================================================
// Dukascopy XAUUSD M1(bid+ask) -> MID -> 1m/2m/5m/10m, 지정 UTC 월 구간 [from,to).
// ★ 완전성 검증: 월별로 bid/ask를 받아 교집합 비율(matchRate)·좌우 균형을 확인,
//   불완전하면 그 달을 자동 재수집(최대 8회, 백오프). throttling 갭 방지.
// 출력: ./parts/{label}_{tf}.csv (헤더/BOM 없는 raw 행). 가격 MID, time=epoch초.
// ============================================================
import { getHistoricalRates } from 'dukascopy-node';
import fs from 'fs';
import path from 'path';

const [, , fromISO, toISO, label] = process.argv;
if (!fromISO || !toISO || !label) { console.error('usage: node fetch_slice.mjs <fromISO> <toISO> <label>'); process.exit(1); }

const KST_OFFSET = 9 * 3600 * 1000;
const START_MS = Date.UTC(2020, 0, 1, 0, 0) - KST_OFFSET;
const END_MS   = Date.UTC(2026, 5, 16, 9, 0) - KST_OFFSET;
const TFS = { '1m': 60000, '2m': 120000, '5m': 300000, '10m': 600000 };

const PARTS = path.resolve('parts');
fs.mkdirSync(PARTS, { recursive: true });
const streams = {};
for (const tf of Object.keys(TFS)) {
  streams[tf] = { s: fs.createWriteStream(path.join(PARTS, `${label}_${tf}.csv`), { encoding: 'utf8' }), count: 0 };
}

async function rawFetch(opts, tries = 4) {
  for (let i = 1; i <= tries; i++) {
    try { return await getHistoricalRates(opts); }
    catch (e) { if (i === tries) throw e; await new Promise(r => setTimeout(r, 2000 * i)); }
  }
}

// 한 달을 완전하게 받을 때까지 재시도
async function fetchMonthComplete(from, to, tag) {
  const common = {
    instrument: 'xauusd', dates: { from, to }, timeframe: 'm1', volumes: true, format: 'json',
    useCache: true, cacheFolderPath: path.resolve('.cache', label),   // 받은 파일 캐시 → 재시도 시 빠진 것만
    batchSize: 8, pauseBetweenBatchesMs: 300,                          // 서버에 덜 공격적 → throttle 예방
    retryCount: 6, retryOnEmpty: true, failAfterRetryCount: false, pauseBetweenRetriesMs: 1200,
  };
  let best = null;
  for (let attempt = 1; attempt <= 8; attempt++) {
    const bid = await rawFetch({ ...common, priceType: 'bid' });
    const ask = await rawFetch({ ...common, priceType: 'ask' });
    const askMap = new Map(ask.map(r => [r.timestamp, r]));
    const mid = [];
    for (const b of bid) {
      const a = askMap.get(b.timestamp);
      if (!a) continue;
      mid.push({ ts: b.timestamp, o: (b.open + a.open) / 2, h: (b.high + a.high) / 2, l: (b.low + a.low) / 2, c: (b.close + a.close) / 2, v: (b.volume || 0) + (a.volume || 0) });
    }
    const minLen = Math.min(bid.length, ask.length);
    const matchRate = minLen ? mid.length / minLen : 0;
    const balance = Math.max(bid.length, ask.length) ? minLen / Math.max(bid.length, ask.length) : 0;
    const ok = bid.length > 0 && ask.length > 0 && matchRate >= 0.95 && balance >= 0.9;
    if (!best || mid.length > best.mid.length) best = { mid, bid: bid.length, ask: ask.length, matchRate, balance };
    if (ok) { best.mid.sort((x, y) => x.ts - y.ts); return best; }
    console.log(`[${label}] ${tag} 불완전(bid=${bid.length} ask=${ask.length} match=${matchRate.toFixed(2)} bal=${balance.toFixed(2)}) 재시도 ${attempt}/8`);
    await new Promise(r => setTimeout(r, 4000 * attempt));
  }
  console.log(`[${label}] ${tag} ★최종 불완전 — 최선본 사용(mid=${best.mid.length})`);
  best.mid.sort((x, y) => x.ts - y.ts);
  return best;
}

function resampleAndWrite(midRows) {
  for (const [tf, size] of Object.entries(TFS)) {
    const buckets = new Map();
    for (const r of midRows) {
      const b = Math.floor(r.ts / size) * size;
      let o = buckets.get(b);
      if (!o) buckets.set(b, { o: r.o, h: r.h, l: r.l, c: r.c, v: r.v });
      else { o.h = Math.max(o.h, r.h); o.l = Math.min(o.l, r.l); o.c = r.c; o.v += r.v; }
    }
    for (const k of [...buckets.keys()].sort((a, b) => a - b)) {
      if (k < START_MS || k > END_MS) continue;
      const o = buckets.get(k);
      streams[tf].s.write(`${Math.round(k / 1000)},${o.o},${o.h},${o.l},${o.c},${o.v.toFixed(4)}\n`);
      streams[tf].count++;
    }
  }
}

function* months(from, to) {
  let cur = new Date(from);
  const end = new Date(to);
  while (cur < end) {
    const nxt = new Date(Date.UTC(cur.getUTCFullYear(), cur.getUTCMonth() + 1, 1));
    yield { from: cur, to: nxt };
    cur = nxt;
  }
}

console.log(`[${label}] 시작 ${fromISO} ~ ${toISO}`);
for (const { from, to } of months(fromISO, toISO)) {
  const tag = from.toISOString().slice(0, 7);
  const res = await fetchMonthComplete(from, to, tag);
  resampleAndWrite(res.mid);
  console.log(`[${label}] ${tag} mid=${res.mid.length} match=${res.matchRate.toFixed(3)} 누적2m=${streams['2m'].count}`);
}
for (const tf of Object.keys(streams)) await new Promise(res => streams[tf].s.end(res));
console.log(`[${label}] 완료 (2m=${streams['2m'].count})`);
