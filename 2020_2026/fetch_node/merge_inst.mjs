// merge_inst.mjs <instrument> <labelsCsv> <outputPatternOrFile> [tfCsv]
//
// Examples:
//   node merge_inst.mjs eurusd eur2010,eur2011,eur2012 eurusd_{tf}_2010-01-01_2026-06-16.csv 1m,2m,5m,10m
//   node merge_inst.mjs xauusd xau2010,xau2011 xauusd_{tf}_2010-01-01_2019-12-31.csv
//
// Reads parts/{label}_{tf}.csv in label order and writes final CSV files to the
// project root (parent of this fetch_node directory). Output includes UTF-8 BOM,
// the exact header, sorted ascending rows, and no duplicate timestamps.
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';

const [, , instrument, labelsArg, outputArg, tfArg = '1m,2m,5m,10m'] = process.argv;

if (!instrument || !labelsArg || !outputArg) {
  console.error('usage: node merge_inst.mjs <instrument> <labelsCsv> <outputPatternOrFile> [tfCsv]');
  process.exit(1);
}

const cwd = process.cwd();
const projectRoot = path.resolve(cwd, '..');
const partsDir = path.resolve(cwd, 'parts');
const labels = labelsArg.split(',').map(s => s.trim()).filter(Boolean);
const tfs = tfArg.split(',').map(s => s.trim()).filter(Boolean);
const protectedPatterns = [
  /^xauusd_.*_2020-01-01_2026-06-16\.csv$/i,
  /^signals_/i,
  /^sim_/i,
  /\.html$/i,
  /^ktr_/i,
];

function outputPathForTf(tf) {
  const file = outputArg.includes('{tf}') ? outputArg.replaceAll('{tf}', tf) : outputArg;
  const base = path.basename(file);
  if (protectedPatterns.some(re => re.test(base))) {
    throw new Error(`refusing to write protected output: ${base}`);
  }
  const out = path.resolve(projectRoot, base);
  if (path.dirname(out) !== projectRoot) {
    throw new Error(`refusing to write outside project root: ${out}`);
  }
  return out;
}

async function readPartRows(file, rows, seen) {
  if (!fs.existsSync(file)) {
    console.warn(`missing part: ${file}`);
    return { read: 0, added: 0, duplicates: 0 };
  }

  const rl = readline.createInterface({
    input: fs.createReadStream(file, { encoding: 'utf8' }),
    crlfDelay: Infinity,
  });

  let read = 0;
  let added = 0;
  let duplicates = 0;
  for await (const rawLine of rl) {
    const line = rawLine.charCodeAt(0) === 0xfeff ? rawLine.slice(1) : rawLine;
    if (!line || line === 'time,open,high,low,close,volume') continue;
    const comma = line.indexOf(',');
    if (comma <= 0) continue;
    const ts = Number(line.slice(0, comma));
    if (!Number.isFinite(ts)) continue;
    read++;
    if (seen.has(ts)) {
      duplicates++;
      continue;
    }
    seen.add(ts);
    rows.push({ ts, line });
    added++;
  }
  return { read, added, duplicates };
}

async function mergeTf(tf) {
  const rows = [];
  const seen = new Set();
  const stats = [];

  for (const label of labels) {
    const part = path.join(partsDir, `${label}_${tf}.csv`);
    const stat = await readPartRows(part, rows, seen);
    stats.push({ label, ...stat });
  }

  rows.sort((a, b) => a.ts - b.ts);

  const out = outputPathForTf(tf);
  const stream = fs.createWriteStream(out, { encoding: 'utf8' });
  stream.write('\ufefftime,open,high,low,close,volume\n');
  for (const row of rows) stream.write(`${row.line}\n`);
  await new Promise((resolve, reject) => {
    stream.end(resolve);
    stream.on('error', reject);
  });

  const duplicateCount = stats.reduce((sum, s) => sum + s.duplicates, 0);
  console.log(`${path.basename(out)} rows=${rows.length} duplicate_parts=${duplicateCount}`);
}

for (const tf of tfs) {
  await mergeTf(tf);
}
