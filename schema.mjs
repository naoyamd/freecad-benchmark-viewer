export const SCHEMA = 'freecad-benchmark/v1';
const states = new Set(['pass', 'fail', 'pending', 'unverified']);
const finite = (v) => typeof v === 'number' && Number.isFinite(v);
const demand = (test, message) => { if (!test) throw new Error(message); };

export function validateBundle(data) {
  demand(data && data.schema === SCHEMA, `schema は ${SCHEMA} を指定してください。`);
  demand(data.run && typeof data.run.id === 'string' && data.run.id.trim() && typeof data.run.title === 'string', 'run.id と run.title が必要です。');
  for (const key of ['model', 'specVersion']) demand(data.run[key] == null || typeof data.run[key] === 'string', `run.${key} は文字列が必要です。`);
  demand(data.run.sourceFiles == null || (Array.isArray(data.run.sourceFiles) && data.run.sourceFiles.every(s => typeof s === 'string')), 'run.sourceFiles はファイル名の配列が必要です。');
  demand(data.assembly?.units == null || data.assembly.units === 'mm', 'メッシュの単位はmmが必要です。');
  demand(Array.isArray(data.parts) && data.parts.length <= 10000, 'parts が不正、または部品数が多すぎます。');
  const ids = new Set();
  let totalVertices = 0;
  for (const p of data.parts) {
    demand(p && typeof p.id === 'string' && p.id && !ids.has(p.id), '部品IDが未指定、または重複しています。');
    ids.add(p.id);
    demand(typeof p.name === 'string', `${p.id}: 部品名が必要です。`);
    demand(Array.isArray(p.vertices) && p.vertices.length >= 9 && p.vertices.length % 3 === 0 && p.vertices.every(finite), `${p.id}: 頂点座標が不正です。`);
    const count = p.vertices.length / 3;
    totalVertices += count;
    demand(totalVertices <= 5000000, '頂点数が上限（500万）を超えています。');
    demand(Array.isArray(p.indices) && p.indices.length >= 3 && p.indices.length % 3 === 0 && p.indices.every(i => Number.isInteger(i) && i >= 0 && i < count), `${p.id}: 三角形の頂点番号が不正です。`);
    demand(!p.color || /^#[0-9a-f]{6}$/i.test(p.color), `${p.id}: 色は #RRGGBB で指定してください。`);
    demand(p.volumeMm3 == null || (finite(p.volumeMm3) && p.volumeMm3 >= 0), `${p.id}: 体積が不正です。`);
  }
  const e = data.evaluation;
  demand(e && ['unverified', 'self-reported', 'verified'].includes(e.status), 'evaluation.status が不正です。');
  demand(e.source == null || typeof e.source === 'string', 'evaluation.source は根拠を示す文字列が必要です。');
  demand(finite(e.maxScore) && e.maxScore > 0, 'maxScore は正の数が必要です。');
  demand(e.score === null || (finite(e.score) && e.score >= 0 && e.score <= e.maxScore), 'score は null または採点範囲内の数値が必要です。');
  for (const key of ['gates', 'metrics', 'issues']) demand(Array.isArray(e[key]), `evaluation.${key} は配列が必要です。`);
  const gates = new Set();
  for (const g of e.gates) {
    demand(g && typeof g.id === 'string' && !gates.has(g.id) && typeof g.label === 'string' && states.has(g.status), 'ゲートのID・名称・状態が不正です。');
    gates.add(g.id);
  }
  for (const m of e.metrics) demand(m && typeof m.label === 'string' && (m.value === null || typeof m.value === 'string' || finite(m.value)), '指標の名称・値が不正です。');
  if (e.categories) {
    demand(Array.isArray(e.categories), '採点内訳は配列が必要です。');
    for (const c of e.categories) demand(c && typeof c.label === 'string' && finite(c.maxScore) && c.maxScore > 0 && (c.score === null || (finite(c.score) && c.score >= 0 && c.score <= c.maxScore)), '採点内訳の名称・配点・得点が不正です。');
    demand(e.categories.reduce((sum, c) => sum + c.maxScore, 0) === e.maxScore, '採点内訳の配点合計がmaxScoreと一致しません。');
    if (e.categories.every(c => c.score !== null) && e.score !== null) demand(Math.abs(e.categories.reduce((sum, c) => sum + c.score, 0) - e.score) < 0.001, '採点内訳の合計がscoreと一致しません。');
  }
  for (const issue of e.issues) demand(typeof issue === 'string', 'issues の項目は文字列で指定してください。');
  if (data.timeseries) {
    demand(typeof data.timeseries.name === 'string' && Array.isArray(data.timeseries.series), '時刻歴の形式が不正です。');
    for (const s of data.timeseries.series) demand(s && typeof s.name === 'string' && Array.isArray(s.values) && s.values.every(v => Array.isArray(v) && v.length === 2 && v.every(finite)), '時刻歴に不正な値があります。');
  }
  return data;
}

export function parseCSV(text) {
  const rows = [];
  let row = [], cell = '', quoted = false, closed = false;
  text = text.replace(/^\uFEFF/, '');
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '"') {
      if (quoted && text[i + 1] === '"') { cell += '"'; i++; }
      else { demand(quoted || (cell === '' && !closed), 'CSVの引用符が不正です。'); closed = quoted; quoted = !quoted; }
    } else if (!quoted && (c === ',' || c === '\n' || c === '\r')) {
      row.push(cell); cell = ''; closed = false;
      if (c !== ',') {
        if (c === '\r' && text[i + 1] === '\n') i++;
        if (row.some(v => v !== '')) rows.push(row);
        row = [];
      }
    } else { demand(!closed, 'CSVの閉じ引用符の後に余分な文字があります。'); cell += c; }
  }
  demand(!quoted, 'CSVの引用符が閉じられていません。');
  if (cell !== '' || row.length) { row.push(cell); rows.push(row); }
  demand(rows.length > 0, 'CSVが空です。');
  const headers = rows.shift();
  demand(headers.every(Boolean) && new Set(headers).size === headers.length, 'CSVの列名が空、または重複しています。');
  demand(rows.every(r => r.length === headers.length), 'CSVの列数が揃っていません。');
  return { headers, rows };
}

export function summary(data) {
  const e = data.evaluation;
  return {
    parts: data.parts.length,
    triangles: data.parts.reduce((n, p) => n + p.indices.length / 3, 0),
    passed: e.gates.filter(g => g.status === 'pass').length,
    failed: e.gates.filter(g => g.status === 'fail').length,
    total: e.gates.length,
    // A score never overrides a missing gate or an unverified review.
    ready: data.parts.length > 0 && e.status === 'verified' && e.score !== null && e.score / e.maxScore >= 0.9 && ['G1', 'G2', 'G3', 'G4', 'G5'].every(id => e.gates.some(g => g.id === id && g.status === 'pass')) && e.gates.every(g => g.status === 'pass'),
  };
}
