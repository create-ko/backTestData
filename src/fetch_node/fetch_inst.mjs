// fetch_inst.mjs <fromISO> <toISO> <label> <instrument> <clipFromISO> <clipToISO>
// 일반화 버전: 임의 instrument(eurusd/gbpusd/usdjpy/xauusd) + 임의 기간 + 정밀도 반올림.
// Dukascopy M1 bid/ask -> MID -> 1m/2m/5m/10m. 출력 parts/{label}_{tf}.csv (raw, time=epoch초).
// 완결성: 월별 bid/ask 교집합 비율 검증 + 자동 재수집(최대 8회).
import { getHistoricalRates } from 'dukascopy-node';
import fs from 'fs';
import path from 'path';

const [, , fromISO, toISO, label, instrument='xauusd', clipFrom, clipTo] = process.argv;
if (!fromISO || !toISO || !label) { console.error('usage: node fetch_inst.mjs <fromISO> <toISO> <label> <instrument> [clipFrom] [clipTo]'); process.exit(1); }

// 정밀도(소수자릿수): MID float 노이즈 제거 + 일관성
const PREC = { eurusd: 6, gbpusd: 6, usdjpy: 4, xauusd: 3, usatechidxusd: 3 };
const prec = PREC[instrument] ?? 5;
const rnd = (v) => Number(v.toFixed(prec));

const KST_OFFSET_MS = 9 * 3600 * 1000;
const DAY_MS = 24 * 3600 * 1000;

function parseClipBoundary(value, isEnd) {
  if (!value) return NaN;
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const kstStartAsUtc = Date.parse(`${value}T00:00:00Z`) - KST_OFFSET_MS;
    return isEnd ? kstStartAsUtc + DAY_MS : kstStartAsUtc;
  }
  const parsed = Date.parse(value);
  return isEnd && /^\d{4}-\d{2}-\d{2}T00:00/.test(value) ? parsed + DAY_MS : parsed;
}

const START_MS = parseClipBoundary(clipFrom || fromISO, false);
const END_MS   = parseClipBoundary(clipTo   || toISO, true);
if (!Number.isFinite(START_MS) || !Number.isFinite(END_MS) || START_MS >= END_MS) {
  console.error(`invalid clip range: start=${clipFrom || fromISO} end=${clipTo || toISO}`);
  process.exit(1);
}
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
async function fetchMonthComplete(from, to, tag) {
  const common = {
    instrument, dates: { from, to }, timeframe: 'm1', volumes: true, format: 'json',
    useCache: true, cacheFolderPath: path.resolve('.cache', label),
    batchSize: 8, pauseBetweenBatchesMs: 300,
    // Empty hourly files are normal during weekends and market closures. Retrying
    // those files multiplies runtime without improving completeness; the monthly
    // bid/ask match and balance checks below still catch incomplete downloads.
    retryCount: 6, retryOnEmpty: false, failAfterRetryCount: false, pauseBetweenRetriesMs: 1200,
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
  console.log(`[${label}] ${tag} ★최종 불완전 — 최선본(mid=${best.mid.length})`);
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
      if (k < START_MS || k >= END_MS) continue;
      const o = buckets.get(k);
      streams[tf].s.write(`${Math.round(k / 1000)},${rnd(o.o)},${rnd(o.h)},${rnd(o.l)},${rnd(o.c)},${o.v.toFixed(4)}\n`);
      streams[tf].count++;
    }
  }
}
function* months(from, to) {
  let cur = new Date(from);
  const end = new Date(to);
  while (cur < end) {
    const monthEnd = new Date(Date.UTC(cur.getUTCFullYear(), cur.getUTCMonth() + 1, 1));
    const nxt = monthEnd < end ? monthEnd : end;
    yield { from: cur, to: nxt };
    cur = nxt;
  }
}
console.log(`[${label}] ${instrument} ${fromISO}~${toISO} prec=${prec} clip=[${clipFrom||fromISO},${clipTo||toISO})`);
for (const { from, to } of months(fromISO, toISO)) {
  const tag = from.toISOString().slice(0, 7);
  const res = await fetchMonthComplete(from, to, tag);
  resampleAndWrite(res.mid);
  console.log(`[${label}] ${tag} mid=${res.mid.length} match=${res.matchRate.toFixed(3)} 누적10m=${streams['10m'].count}`);
}
for (const tf of Object.keys(streams)) await new Promise(res => streams[tf].s.end(res));
fs.writeFileSync(path.join(PARTS, `${label}.done`), 'ok\n', 'ascii');
console.log(`[${label}] complete (10m=${streams['10m'].count})`);
process.exit(0);
console.log(`[${label}] 완료 (10m=${streams['10m'].count})`);
