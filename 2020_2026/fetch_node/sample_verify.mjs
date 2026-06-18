// sample_verify.mjs <instrument> <fromISO> <toISO>
// FX/instrument 1개월 샘플 검증: MID·정밀도·시간대·KTR 산출 가능성 확인용. parts에 안 씀.
import { getHistoricalRates } from 'dukascopy-node';

const [, , inst='eurusd', fromISO='2024-01-01', toISO='2024-02-01'] = process.argv;
const TF=600000; // 10m

async function rawFetch(opts, tries=4){
  for(let i=1;i<=tries;i++){
    try{ return await getHistoricalRates(opts);}catch(e){ if(i===tries) throw e; await new Promise(r=>setTimeout(r,2000*i)); }
  }
}
const common={ instrument:inst, dates:{from:new Date(fromISO),to:new Date(toISO)}, timeframe:'m1',
  volumes:true, format:'json', useCache:false, batchSize:8, pauseBetweenBatchesMs:300,
  retryCount:6, retryOnEmpty:true, failAfterRetryCount:false, pauseBetweenRetriesMs:1200 };
console.log(`[${inst}] ${fromISO}~${toISO} m1 bid/ask 수집...`);
const bid=await rawFetch({...common,priceType:'bid'});
const ask=await rawFetch({...common,priceType:'ask'});
const askMap=new Map(ask.map(r=>[r.timestamp,r]));
const mid=[];
for(const b of bid){ const a=askMap.get(b.timestamp); if(!a) continue;
  mid.push({ts:b.timestamp,o:(b.open+a.open)/2,h:(b.high+a.high)/2,l:(b.low+a.low)/2,c:(b.close+a.close)/2}); }
mid.sort((x,y)=>x.ts-y.ts);
console.log(`bid=${bid.length} ask=${ask.length} mid=${mid.length} match=${(mid.length/Math.min(bid.length,ask.length)).toFixed(3)}`);
// 스프레드(첫 100개 평균) — 정밀도 감
let sp=0,c=0; for(const b of bid.slice(0,200)){const a=askMap.get(b.timestamp); if(a){sp+=(a.close-b.close);c++;}}
console.log(`평균 스프레드(close, 첫200): ${(sp/c).toFixed(6)}`);
// 10m 리샘플
const buckets=new Map();
for(const r of mid){ const k=Math.floor(r.ts/TF)*TF; let o=buckets.get(k);
  if(!o) buckets.set(k,{o:r.o,h:r.h,l:r.l,c:r.c}); else {o.h=Math.max(o.h,r.h);o.l=Math.min(o.l,r.l);o.c=r.c;} }
const keys=[...buckets.keys()].sort((a,b)=>a-b);
console.log(`10m 봉 ${keys.length}개`);
function kst(ms){ return new Date(ms+9*3600000).toISOString().slice(0,16).replace('T',' '); }
console.log('--- 첫 3봉 (KST) ---');
for(const k of keys.slice(0,3)){const o=buckets.get(k); console.log(`${kst(k)}  O=${o.o} H=${o.h} L=${o.l} C=${o.c}`);}
console.log('--- 끝 3봉 (KST) ---');
for(const k of keys.slice(-3)){const o=buckets.get(k); console.log(`${kst(k)}  O=${o.o} H=${o.h} L=${o.l} C=${o.c}`);}
// 가격 범위·소수자릿수
const prices=keys.map(k=>buckets.get(k).c);
console.log(`종가 범위: ${Math.min(...prices)} ~ ${Math.max(...prices)}`);
const decimals=Math.max(...prices.slice(0,50).map(p=>{const s=String(p);const i=s.indexOf('.');return i<0?0:s.length-i-1;}));
console.log(`관측 최대 소수자릿수(원시 MID): ${decimals} → float 노이즈 가능, 반올림 필요`);
