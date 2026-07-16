import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';

const DATA = path.resolve('..', '..', 'data');
const PARTS = path.resolve('parts');
const TFS = ['1m', '2m', '5m', '10m'];
const allInstruments = ['eurusd', 'gbpusd', 'usdjpy', 'xauusd'];
const instrumentArg = process.argv.find(arg => arg.startsWith('--instrument='))?.split('=')[1];
const instruments = instrumentArg ? allInstruments.filter(inst => inst === instrumentArg) : allInstruments;
if (instruments.length === 0) throw new Error(`unsupported instrument: ${instrumentArg}`);
const includeUsatech = process.argv.includes('--usatech');
const mergeOnly = process.argv.includes('--merge-only');
fs.mkdirSync(PARTS, { recursive: true });

const tasks = [];
for (const inst of instruments) {
  if (doneWhole(inst)) continue;
  for (let day = 17; day <= 30; day++) {
    const clip = `2026-06-${String(day).padStart(2, '0')}`;
    const d = new Date(`${clip}T00:00:00Z`);
    const from = new Date(d.getTime() - 86400000).toISOString().slice(0, 10);
    const to = new Date(d.getTime() + 86400000).toISOString().slice(0, 10);
    tasks.push({ inst, label: `${inst}_202606${String(day).padStart(2, '0')}_kst`, from, to, clipFrom: clip, clipTo: clip });
  }
}
if (includeUsatech) for (let year = 2011; year <= 2026; year++) tasks.push({
  inst: 'usatechidxusd', label: `usatech_${year}`, from: year === 2011 ? '2011-09-19' : `${year}-01-01`,
  to: year === 2026 ? '2026-07-01' : `${year + 1}-01-01`,
  clipFrom: year === 2011 ? '2011-09-19' : `${year}-01-01`, clipTo: year === 2026 ? '2026-06-30' : `${year}-12-31`,
});

const done = label => fs.existsSync(path.join(PARTS, `${label}.done`));
function doneWhole(inst) { return TFS.every(tf => { try { return fs.statSync(path.join(PARTS, `${inst}_20260617_20260630_${tf}.csv`)).size > 0; } catch { return false; } }); }
function fetchOne(t) {
  return new Promise((resolve, reject) => {
    if (done(t.label)) { console.log(`[skip] ${t.label}`); return resolve(); }
    console.log(`[start] ${t.label}`);
    const child = spawn(process.execPath, ['fetch_inst.mjs', t.from, t.to, t.label, t.inst, t.clipFrom, t.clipTo], { stdio: 'inherit' });
    child.once('error', reject);
    child.once('close', code => code === 0 ? resolve() : reject(new Error(`${t.label} exit=${code}`)));
  });
}
async function pool(items, n) {
  let i = 0;
  await Promise.all(Array.from({ length: Math.min(n, items.length) }, async () => {
    while (i < items.length) await fetchOne(items[i++]);
  }));
}

async function writeMerged(files, output, hasHeaders) {
  const out = fs.createWriteStream(output, { encoding: 'utf8' });
  out.write('\ufefftime,open,high,low,close,volume\n');
  let last = -Infinity, rows = 0, duplicates = 0;
  for (const file of files) {
    if (!fs.existsSync(file)) throw new Error(`missing input: ${file}`);
    const rl = readline.createInterface({ input: fs.createReadStream(file, { encoding: 'utf8' }), crlfDelay: Infinity });
    for await (const raw of rl) {
      const line = raw.charCodeAt(0) === 0xfeff ? raw.slice(1) : raw;
      if (!line || (hasHeaders && line.startsWith('time,'))) continue;
      const comma = line.indexOf(',');
      const ts = Number(line.slice(0, comma));
      if (!Number.isFinite(ts)) continue;
      if (ts === last) { duplicates++; continue; }
      if (ts < last) throw new Error(`non-monotonic ${path.basename(output)}: ${ts} < ${last}`);
      out.write(`${line}\n`); last = ts; rows++;
    }
  }
  await new Promise((resolve, reject) => { out.end(resolve); out.on('error', reject); });
  console.log(`[merged] ${path.basename(output)} rows=${rows} duplicates=${duplicates}`);
}

console.log(`fetch tasks=${tasks.length}, concurrency=1, mergeOnly=${mergeOnly}`);
if (!mergeOnly) await pool(tasks, 1);
for (const inst of instruments) {
  if (doneWhole(inst)) continue;
  const dailyComplete = Array.from({ length: 14 }, (_, i) => `202606${String(17 + i).padStart(2, '0')}`)
    .every(day => done(`${inst}_${day}_kst`));
  if (!dailyComplete) { console.log(`[incomplete] ${inst}: daily parts not merged`); continue; }
  for (const tf of TFS) await writeMerged(
    Array.from({ length: 14 }, (_, i) => path.join(PARTS, `${inst}_202606${String(17 + i).padStart(2, '0')}_kst_${tf}.csv`)),
    path.join(PARTS, `${inst}_20260617_20260630_${tf}.csv`), false,
  );
}
for (const inst of instruments) {
  if (!doneWhole(inst)) { console.log(`[incomplete] ${inst}: final file not written`); continue; }
  for (const tf of TFS) await writeMerged([
  path.join(DATA, `${inst}_${tf}_2010-01-01_2026-06-16.csv`),
  path.join(PARTS, `${inst}_20260617_20260630_${tf}.csv`),
  ], path.join(DATA, `${inst}_${tf}_2010-01-01_2026-06-30.csv`), true);
}
if (includeUsatech) for (const tf of TFS) await writeMerged(
  Array.from({ length: 16 }, (_, i) => path.join(PARTS, `usatech_${2011 + i}_${tf}.csv`)),
  path.join(DATA, `usatechidxusd_${tf}_2011-09-19_2026-06-30.csv`), false,
);
console.log('all downloads and merges complete');
