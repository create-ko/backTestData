import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import readline from 'node:readline';
import { spawn } from 'node:child_process';
import { pathToFileURL } from 'node:url';

const ROOT = path.resolve('..');
const HERE = path.resolve('.');
const PARTS = path.join(HERE, 'parts');
const TFS = ['1m', '2m', '5m', '10m'];
const TF_SECONDS = { '1m': 60, '2m': 120, '5m': 300, '10m': 600 };
const KST_OFFSET_SECONDS = 9 * 3600;
const DAY_MS = 24 * 3600 * 1000;
const DEFAULT_CONCURRENCY = Number(process.env.FETCH_CONCURRENCY || 4);

const protectedOutput = /^xauusd_.*_2020-01-01_2026-06-16\.csv$/i;

export function kstDate(sec) {
  return new Date((sec + KST_OFFSET_SECONDS) * 1000).toISOString().slice(0, 10);
}

function addDays(iso, days) {
  const ms = Date.parse(`${iso}T00:00:00Z`) + days * DAY_MS;
  return new Date(ms).toISOString().slice(0, 10);
}

function yearsInclusive(start, end) {
  const years = [];
  for (let y = start; y <= end; y++) years.push(y);
  return years;
}

export function buildTargets() {
  const majors = ['eurusd', 'gbpusd', 'usdjpy'].map(instrument => ({
    instrument,
    start: '2010-01-01',
    end: '2026-06-16',
    years: yearsInclusive(2010, 2026),
    outputPattern: `${instrument}_{tf}_2010-01-01_2026-06-16.csv`,
  }));
  const xau = {
    instrument: 'xauusd',
    start: '2010-01-01',
    end: '2019-12-31',
    years: yearsInclusive(2010, 2019),
    outputPattern: 'xauusd_{tf}_2010-01-01_2019-12-31.csv',
  };
  return [...majors, xau].map(target => ({
    ...target,
    labels: target.years.map(year => `${target.instrument}_${year}`),
  }));
}

export function buildFinalCsvs(targets = buildTargets()) {
  return targets.flatMap(target => TFS.map(tf => target.outputPattern.replaceAll('{tf}', tf)));
}

function clipForYear(target, year) {
  const from = `${year}-01-01`;
  const nominalTo = `${year}-12-31`;
  const to = nominalTo > target.end ? target.end : nominalTo;
  return { from, to };
}

function makeJob(target, year) {
  const clip = clipForYear(target, year);
  return {
    instrument: target.instrument,
    year,
    label: `${target.instrument}_${year}`,
    fetchFrom: addDays(clip.from, -1),
    fetchTo: addDays(clip.to, 1),
    clipFrom: clip.from,
    clipTo: clip.to,
  };
}

async function ensureDirs() {
  await fsp.mkdir(PARTS, { recursive: true });
  await assertWritable(PARTS);
  await assertWritable(ROOT);
}

async function assertWritable(dir) {
  const probe = path.join(dir, `.write_probe_${Date.now()}_${Math.random().toString(16).slice(2)}`);
  try {
    await fsp.writeFile(probe, 'probe\n', 'utf8');
    await fsp.unlink(probe);
  } catch (error) {
    throw new Error(`directory is not writable by Node runtime: ${dir} (${error.code || error.message})`);
  }
}

async function partStats(label) {
  const stats = {};
  for (const tf of TFS) {
    const file = path.join(PARTS, `${label}_${tf}.csv`);
    try {
      const st = await fsp.stat(file);
      stats[tf] = st.size;
    } catch {
      stats[tf] = 0;
    }
  }
  return stats;
}

async function verifyPart(label) {
  const stats = await partStats(label);
  const missing = Object.entries(stats).filter(([, size]) => size <= 0).map(([tf]) => tf);
  if (missing.length) throw new Error(`${label} empty/missing part files: ${missing.join(',')}`);
  console.log(`[parts] ${label} ${TFS.map(tf => `${tf}=${stats[tf]}`).join(' ')}`);
}

function runProcess(args) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, args, { cwd: HERE, stdio: ['ignore', 'pipe', 'pipe'] });
    const tail = [];
    const remember = (prefix, chunk) => {
      for (const line of chunk.toString('utf8').split(/\r?\n/).filter(Boolean)) {
        tail.push(`${prefix}${line}`);
        if (tail.length > 120) tail.shift();
      }
    };
    child.stdout.on('data', chunk => remember('', chunk));
    child.stderr.on('data', chunk => remember('ERR: ', chunk));
    child.on('error', error => {
      tail.push(`spawn error: ${error.stack || error}`);
      resolve({ code: -1, error, tail });
    });
    child.on('close', code => {
      resolve({ code, tail });
    });
  });
}

async function runFetchJob(job) {
  const args = ['fetch_inst.mjs', job.fetchFrom, job.fetchTo, job.label, job.instrument, job.clipFrom, job.clipTo];
  for (let attempt = 1; attempt <= 2; attempt++) {
    console.log(`[fetch] ${job.label} attempt ${attempt}/2 fetch=${job.fetchFrom}..${job.fetchTo} clipKST=${job.clipFrom}..${job.clipTo}`);
    const res = await runProcess(args);
    if (res.code === 0) {
      await verifyPart(job.label);
      return;
    }
    console.warn(`[fetch] ${job.label} failed with exit ${res.code}`);
    if (res.tail?.length) console.warn(res.tail.slice(-20).join('\n'));
  }
  throw new Error(`${job.label} failed after retry`);
}

async function runPool(jobs, concurrency) {
  const queue = [...jobs];
  const failures = [];
  async function worker(id) {
    while (queue.length) {
      const job = queue.shift();
      try {
        await runFetchJob(job);
      } catch (error) {
        failures.push({ job, error });
        console.error(`[worker ${id}] ${job.label}: ${error.message}`);
      }
    }
  }
  await Promise.all(Array.from({ length: concurrency }, (_, i) => worker(i + 1)));
  if (failures.length) {
    throw new Error(`${failures.length} fetch jobs failed: ${failures.map(f => f.job.label).join(', ')}`);
  }
}

async function runMerge(target) {
  for (const tf of TFS) {
    const outputName = target.outputPattern.replaceAll('{tf}', tf);
    if (protectedOutput.test(outputName)) throw new Error(`refusing protected output ${outputName}`);
  }
  const args = ['merge_inst.mjs', target.instrument, target.labels.join(','), target.outputPattern, TFS.join(',')];
  console.log(`[merge] ${target.instrument} -> ${target.outputPattern}`);
  const res = await runProcess(args);
  if (res.code !== 0) {
    if (res.tail?.length) console.error(res.tail.slice(-40).join('\n'));
    throw new Error(`merge failed for ${target.instrument}`);
  }
  if (res.tail?.length) console.log(res.tail.join('\n'));
}

function monthKeyFromDate(iso) {
  return iso.slice(0, 7);
}

function monthsInclusive(startIso, endIso) {
  const months = [];
  let y = Number(startIso.slice(0, 4));
  let m = Number(startIso.slice(5, 7));
  const endKey = monthKeyFromDate(endIso);
  while (true) {
    const key = `${y}-${String(m).padStart(2, '0')}`;
    months.push(key);
    if (key === endKey) return months;
    m++;
    if (m === 13) {
      y++;
      m = 1;
    }
  }
}

async function validateCsv(file, startIso, endIso, tf) {
  const full = path.join(ROOT, file);
  const rl = readline.createInterface({
    input: fs.createReadStream(full, { encoding: 'utf8' }),
    crlfDelay: Infinity,
  });
  let headerSeen = false;
  let rows = 0;
  let first = null;
  let last = null;
  let previous = null;
  let duplicate = 0;
  let backward = 0;
  const byMonth = new Map();
  for await (const raw of rl) {
    const line = raw.charCodeAt(0) === 0xfeff ? raw.slice(1) : raw;
    if (!line) continue;
    if (!headerSeen) {
      if (line !== 'time,open,high,low,close,volume') throw new Error(`${file} bad header`);
      headerSeen = true;
      continue;
    }
    const ts = Number(line.slice(0, line.indexOf(',')));
    if (!Number.isFinite(ts)) throw new Error(`${file} invalid timestamp line: ${line.slice(0, 80)}`);
    if (previous !== null) {
      if (ts === previous) duplicate++;
      if (ts < previous) backward++;
    }
    previous = ts;
    first ??= ts;
    last = ts;
    rows++;
    const month = kstDate(ts).slice(0, 7);
    byMonth.set(month, (byMonth.get(month) || 0) + 1);
  }
  if (!headerSeen) throw new Error(`${file} missing header`);
  if (rows <= 0) throw new Error(`${file} has no data rows`);
  if (duplicate || backward) throw new Error(`${file} duplicate=${duplicate} backward=${backward}`);
  const firstKst = kstDate(first);
  const lastKst = kstDate(last);
  if (firstKst !== startIso || lastKst !== endIso) {
    throw new Error(`${file} KST date range ${firstKst}..${lastKst}, expected ${startIso}..${endIso}`);
  }
  const missingMonths = monthsInclusive(startIso, endIso).filter(m => !byMonth.has(m));
  if (missingMonths.length) throw new Error(`${file} missing KST months: ${missingMonths.join(',')}`);
  const monthlyWarnings = [];
  for (const [month, count] of [...byMonth.entries()].sort()) {
    const theoreticalMax = Math.ceil((31 * 24 * 3600) / TF_SECONDS[tf]);
    if (count > theoreticalMax) monthlyWarnings.push(`${month}:${count}>${theoreticalMax}`);
    if (count < 10) monthlyWarnings.push(`${month}:${count}<10`);
  }
  return { file, rows, firstKst, lastKst, duplicate, backward, months: byMonth.size, monthlyWarnings };
}

async function validateAll(targets) {
  const results = [];
  for (const target of targets) {
    for (const tf of TFS) {
      const file = target.outputPattern.replaceAll('{tf}', tf);
      results.push(await validateCsv(file, target.start, target.end, tf));
    }
  }
  return results;
}

function printSummary(results) {
  console.log('\nFinal validation summary');
  console.log('file,rows,kst_start,kst_end,months,warnings');
  for (const r of results) {
    console.log(`${r.file},${r.rows},${r.firstKst},${r.lastKst},${r.months},${r.monthlyWarnings.length ? r.monthlyWarnings.join('|') : 'ok'}`);
  }
}

async function main() {
  await ensureDirs();
  const targets = buildTargets();
  const jobs = targets.flatMap(target => target.years.map(year => makeJob(target, year)));
  console.log(`targets=${targets.length} jobs=${jobs.length} concurrency=${DEFAULT_CONCURRENCY}`);
  await runPool(jobs, DEFAULT_CONCURRENCY);
  for (const target of targets) await runMerge(target);
  const results = await validateAll(targets);
  printSummary(results);
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  main().catch(error => {
    console.error(error.stack || error);
    process.exit(1);
  });
}
