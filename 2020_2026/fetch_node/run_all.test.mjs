import assert from 'node:assert/strict';

const mod = await import('./run_all.mjs?test=1');

const targets = mod.buildTargets();
const finalCsvs = mod.buildFinalCsvs(targets);
assert.equal(targets.length, 4, 'buildTargets should produce four merge groups');
assert.equal(finalCsvs.length, 16, 'driver should produce exactly 16 final CSV files');

const protectedXau = finalCsvs.filter(name => name.includes('xauusd_') && name.includes('2020-01-01_2026-06-16'));
assert.equal(protectedXau.length, 0, 'driver must not target protected 2020+ XAUUSD files');

const eur = targets.find(t => t.instrument === 'eurusd');
assert.ok(eur, 'eurusd target exists');
assert.equal(eur.years.length, 17, 'major pairs should include 2010 through 2026');
assert.equal(eur.labels[0], 'eurusd_2010');
assert.equal(eur.labels.at(-1), 'eurusd_2026');

const xau = targets.find(t => t.instrument === 'xauusd');
assert.ok(xau, 'xauusd target exists');
assert.deepEqual(xau.years, [2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019]);
assert.equal(xau.outputPattern, 'xauusd_{tf}_2010-01-01_2019-12-31.csv');

assert.equal(mod.kstDate(1262271600), '2010-01-01');
assert.equal(mod.kstDate(1577804399), '2019-12-31');
assert.equal(mod.kstDate(1577804400), '2020-01-01');

console.log('run_all self-test passed');
