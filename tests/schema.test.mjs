import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { validateBundle, parseCSV, summary } from '../schema.mjs';
const initial = JSON.parse(await readFile(new URL('../data/benchmark.json', import.meta.url)));
const part = { id: 'leg', name: '試験用三角形', color: '#82a0b1', vertices: [0, 0, 0, 100, 0, 0, 0, 100, 0], indices: [0, 1, 2] };
const copy = () => structuredClone(initial);
test('initial data contains no invented CAD or scores', () => { validateBundle(initial); assert.equal(initial.parts.length, 0); assert.equal(initial.evaluation.score, null); assert.equal(summary(initial).ready, false); });
test('a score cannot override failed, missing or unverified gates', () => {
  const data = copy(); data.parts = [part]; data.evaluation.score = 95; data.evaluation.gates.forEach(g => { g.status = 'pass'; });
  assert.equal(summary(validateBundle(data)).ready, false); data.evaluation.status = 'verified'; assert.equal(summary(data).ready, true);
  data.evaluation.gates[0].status = 'fail'; assert.equal(summary(data).ready, false); data.evaluation.gates.shift(); assert.equal(summary(data).ready, false);
});
test('rejects corrupt mesh and duplicate object identities', () => {
  const data = copy(); data.parts = [structuredClone(part)]; data.parts[0].indices[2] = 100; assert.throws(() => validateBundle(data), /頂点番号/);
  data.parts = [structuredClone(part), structuredClone(part)]; assert.throws(() => validateBundle(data), /重複/);
  data.parts = [structuredClone(part)]; data.parts[0].vertices[0] = NaN; assert.throws(() => validateBundle(data), /頂点座標/);
});
test('rejects unsupported schema, invalid score and review states', () => {
  const data = copy(); data.schema = 'other'; assert.throws(() => validateBundle(data), /schema/); data.schema = initial.schema;
  data.evaluation.score = 101; assert.throws(() => validateBundle(data), /score/); data.evaluation.score = null;
  data.evaluation.status = 'maybe'; assert.throws(() => validateBundle(data), /status/);
});
test('CSV supports BOM, CRLF, quoted commas, escaped quotes and embedded newlines', () => {
  assert.deepEqual(parseCSV('\uFEFFid,note,value\r\nA,"a,b",2\r\nB,"say ""ok""\nnext",3'), { headers: ['id', 'note', 'value'], rows: [['A', 'a,b', '2'], ['B', 'say "ok"\nnext', '3']] });
});
test('CSV rejects inconsistent rows, unclosed quotes and duplicate columns', () => {
  for (const csv of ['a,b\n1', 'a,b\n"x,2', 'a,a\n1,2', 'a,b\n"x"oops,2']) assert.throws(() => parseCSV(csv));
});
test('timeseries rejects non-finite data', () => { const data = copy(); data.timeseries = { name: 'D1', series: [{ name: 'stroke', values: [[0, Infinity]] }] }; assert.throws(() => validateBundle(data), /時刻歴/); });
test('category totals cannot contradict the displayed score', () => { const data = copy(); data.evaluation.score = 95; data.evaluation.categories = [{ label: 'all', score: 50, maxScore: 100 }]; assert.throws(() => validateBundle(data), /合計/); data.evaluation.categories[0].score = 95; validateBundle(data); });
test('rejects an incompatible coordinate unit or malformed provenance', () => { const data = copy(); data.assembly = { units: 'm' }; assert.throws(() => validateBundle(data), /単位/); delete data.assembly; data.evaluation.source = { file: 'report' }; assert.throws(() => validateBundle(data), /source/); });
