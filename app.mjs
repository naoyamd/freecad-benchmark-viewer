import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { SCHEMA, validateBundle, parseCSV, summary } from './schema.mjs';

const $ = id => document.getElementById(id);
const node = (tag, text, className) => { const n = document.createElement(tag); if (text != null) n.textContent = text; if (className) n.className = className; return n; };
const number = n => new Intl.NumberFormat('ja-JP', { maximumFractionDigits: 3 }).format(n);
const reviewNames = { unverified: '独立検証 未実施', 'self-reported': 'モデル自己申告', verified: '独立検証 済み（入力値）' };
const statusNames = { pass: 'Pass', fail: 'Fail', pending: '未確認', unverified: '未検証' };
const palette = ['#8aa8b5', '#536e80', '#a2bcb6', '#a2acb7', '#c49c6a', '#607f8c'];
let bundle, initial, activeTab = 'overview', selected = null;
let csvFiles = [], attachedFiles = [], objectUrls = [];
let scene, renderer, camera, controls, assembly, grid, axes;
let meshes = new Map(), center = new THREE.Vector3(), size = 1000, bbox = new THREE.Box3();
let toastTimer;

function toast(message, error = false) {
  clearTimeout(toastTimer); $('toast').textContent = message; $('toast').className = `toast${error ? ' error' : ''}`; $('toast').hidden = false;
  toastTimer = setTimeout(() => { $('toast').hidden = true; }, error ? 12000 : 5000);
}
function emptyResult(title, detail) {
  const row = node('div', null, 'result-empty'); row.append(node('span', '↗', 'result-empty-icon'));
  const text = node('div'); text.append(node('h3', title), node('p', detail)); row.append(text); return row;
}
function download(blob, filename) {
  const url = URL.createObjectURL(blob), a = node('a'); a.href = url; a.download = filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function init3D() {
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); renderer.setClearColor(0xedf2f5); renderer.localClippingEnabled = true;
    renderer.outputColorSpace = THREE.SRGBColorSpace; renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.35;
    $('viewport').prepend(renderer.domElement); renderer.domElement.setAttribute('aria-label', '3Dアセンブリ。ドラッグで回転、右ドラッグで移動、スクロールでズーム。');
    scene = new THREE.Scene(); scene.add(new THREE.HemisphereLight(0xf4faff, 0x8a9ca5, 2.7));
    const sun = new THREE.DirectionalLight(0xffffff, 3.4); sun.position.set(-800, -600, 1500); scene.add(sun);
    const fill = new THREE.DirectionalLight(0xdbf0ff, 1.7); fill.position.set(900, 500, 400); scene.add(fill);
    camera = new THREE.PerspectiveCamera(36, 1, .1, 100000); camera.up.set(0, 0, 1);
    camera.position.set(1500, -1800, 1100);
    controls = new OrbitControls(camera, renderer.domElement); controls.enableDamping = true; controls.dampingFactor = .12;
    controls.addEventListener('change', render3D);
    assembly = new THREE.Group(); scene.add(assembly);
    grid = new THREE.GridHelper(2000, 20, 0xc0d0d8, 0xdce4e9); grid.rotation.x = Math.PI / 2; scene.add(grid);
    axes = new THREE.AxesHelper(130); scene.add(axes);
    new ResizeObserver(() => { const w = $('viewport').clientWidth, h = $('viewport').clientHeight; if (!h || !w) return; renderer.setSize(w, h); camera.aspect = w / h; camera.updateProjectionMatrix(); render3D(); }).observe($('viewport'));
    let pointerStart;
    renderer.domElement.addEventListener('pointerdown', e => { pointerStart = { x: e.clientX, y: e.clientY }; });
    renderer.domElement.addEventListener('pointerup', e => {
      if (!pointerStart || Math.hypot(e.clientX - pointerStart.x, e.clientY - pointerStart.y) > 5) return;
      const rect = renderer.domElement.getBoundingClientRect(), ray = new THREE.Raycaster();
      ray.setFromCamera(new THREE.Vector2((e.clientX - rect.left) / rect.width * 2 - 1, -(e.clientY - rect.top) / rect.height * 2 + 1), camera);
      const hit = ray.intersectObjects([...meshes.values()].filter(m => m.visible)).find(h => !isClipped(h.point));
      selectPart(hit?.object.userData.id ?? null);
    });
    renderer.setAnimationLoop(() => { controls.update(); });
    render3D();
  } catch (error) {
    renderer = null; $('webgl-error').hidden = false; $('webgl-error').textContent = `WebGLを開始できませんでした。ハードウェアアクセラレーションを確認してください。評価結果とCSVは利用できます。 (${error.message})`;
    ['fit', 'screenshot', 'wireframe', 'transparent', 'explode', 'section', 'section-axis', 'section-position'].forEach(id => { $(id).disabled = true; });
  }
}
function render3D() { if (renderer && scene) renderer.render(scene, camera); }
function clearMeshes() {
  for (const mesh of meshes.values()) { assembly.remove(mesh); mesh.geometry.dispose(); mesh.material.dispose(); }
  meshes.clear(); selected = null;
}
function loadGeometry() {
  if (!renderer) return;
  clearMeshes(); bbox.makeEmpty();
  for (const [i, p] of bundle.parts.entries()) {
    const geometry = new THREE.BufferGeometry(); geometry.setAttribute('position', new THREE.Float32BufferAttribute(p.vertices, 3)); geometry.setIndex(p.indices); geometry.computeVertexNormals(); geometry.computeBoundingBox();
    const material = new THREE.MeshStandardMaterial({ color: p.color || palette[i % palette.length], metalness: .28, roughness: .42, side: THREE.DoubleSide });
    const mesh = new THREE.Mesh(geometry, material); mesh.userData = { id: p.id, centroid: geometry.boundingBox.getCenter(new THREE.Vector3()), baseColor: material.color.clone() }; assembly.add(mesh); meshes.set(p.id, mesh); bbox.union(geometry.boundingBox);
  }
  if (!bbox.isEmpty()) {
    bbox.getCenter(center); size = Math.max(...bbox.getSize(new THREE.Vector3()).toArray(), 1);
    grid.position.set(center.x, center.y, bbox.min.z - size * .007); grid.scale.setScalar(size / 800);
    axes.position.set(bbox.min.x - size * .15, bbox.min.y - size * .15, bbox.min.z); axes.scale.setScalar(size / 1000);
    const dims = bbox.getSize(new THREE.Vector3()); $('bounds-label').textContent = `${number(dims.x)} × ${number(dims.y)} × ${number(dims.z)} mm`;
    setView('iso');
  }
  $('empty-state').hidden = bundle.parts.length > 0; grid.visible = bundle.parts.length > 0; axes.visible = bundle.parts.length > 0;
  updateDisplay();
}
function setView(view = 'iso') {
  if (!renderer) return;
  const dirs = { iso: [1.35, -1.9, 1.05], front: [0, -1, 0], right: [1, 0, 0], top: [0, 0, 1] };
  const direction = new THREE.Vector3(...dirs[view]).normalize();
  const aspect = camera.aspect || 1, half = size * (.85 + Number($('explode').value) / 150);
  const distance = half / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) / Math.min(1, aspect);
  camera.up.set(0, view === 'top' ? 1 : 0, view === 'top' ? 0 : 1);
  controls.target.copy(center); camera.position.copy(center).addScaledVector(direction, distance); camera.near = Math.max(size / 10000, .001); camera.far = distance + size * 100;
  controls.minDistance = size * .03; controls.maxDistance = size * 50; camera.updateProjectionMatrix(); controls.update();
  document.querySelectorAll('[data-view]').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  $('view-label').textContent = { iso: 'ISOMETRIC VIEW', front: 'FRONT · −Y', right: 'RIGHT · +X', top: 'TOP · +Z' }[view]; render3D();
}
function clippingPlane() {
  if (!$('section').checked || bbox.isEmpty()) return null;
  const axis = $('section-axis').value.toLowerCase(), point = bbox.min[axis] + (bbox.max[axis] - bbox.min[axis]) * Number($('section-position').value) / 100;
  const normal = new THREE.Vector3(); normal[axis] = -1; return new THREE.Plane(normal, point);
}
function isClipped(point) { const plane = clippingPlane(); return plane && plane.distanceToPoint(point) < 0; }
function updateDisplay() {
  const explode = Number($('explode').value) / 100, clip = clippingPlane(); $('explode-value').textContent = `${Math.round(explode * 100)}%`;
  for (const mesh of meshes.values()) {
    let offset = mesh.userData.centroid.clone().sub(center);
    if (offset.length() < size * .01) offset.set(size * .15, 0, size * .15);
    mesh.position.copy(offset.multiplyScalar(explode * 1.5));
    mesh.material.wireframe = $('wireframe').checked; mesh.material.transparent = $('transparent').checked; mesh.material.opacity = $('transparent').checked ? .3 : 1;
    mesh.material.depthWrite = !$('transparent').checked; mesh.material.clippingPlanes = clip ? [clip] : []; mesh.material.needsUpdate = true;
  }
  render3D();
}
function selectPart(id) {
  selected = id;
  for (const [key, mesh] of meshes) mesh.material.emissive.set(key === id ? 0x175e53 : 0x000000);
  document.querySelectorAll('.part-row').forEach(n => n.classList.toggle('selected', n.dataset.part === id));
  const p = bundle.parts.find(p => p.id === id), detail = $('part-detail'); detail.replaceChildren(node('span', 'PART INSPECTOR', 'eyebrow'));
  if (p) {
    detail.append(node('strong', p.name)); const dl = node('dl');
    for (const [key, value] of [['ID', p.id], ['材質', p.material || '未登録'], ['体積', p.volumeMm3 == null ? '未登録' : `${number(p.volumeMm3)} mm³`], ['面数', number(p.indices.length / 3)]]) dl.append(node('dt', key), node('dd', value));
    detail.append(dl);
  } else detail.append(node('p', '部品をクリックして詳細を確認'));
  render3D();
}
function updateVisibleCount() { $('visible-count').textContent = `${[...meshes.values()].filter(m => m.visible).length} visible`; }
function renderParts() {
  const list = $('parts-list'); list.replaceChildren();
  if (!bundle.parts.length) list.append(node('div', 'CADの読込後に部品一覧を表示します。', 'parts-empty'));
  bundle.parts.forEach((p, i) => {
    const row = node('div', null, 'part-row'); row.dataset.part = p.id;
    const check = node('input'); check.type = 'checkbox'; check.checked = true; check.setAttribute('aria-label', `${p.name}を表示`);
    check.addEventListener('change', () => { const mesh = meshes.get(p.id); if (mesh) mesh.visible = check.checked; updateVisibleCount(); render3D(); });
    const button = node('button'); const swatch = node('span', null, 'part-color'); swatch.style.background = p.color || palette[i % palette.length]; button.append(swatch, node('span', p.name)); button.title = p.name;
    button.addEventListener('click', () => selectPart(p.id)); row.append(check, button); list.append(row);
  });
  $('tree-count').textContent = bundle.parts.length; $('tree-root-name').textContent = bundle.run.id; updateVisibleCount(); selectPart(null);
}
function renderHeader() {
  const e = bundle.evaluation, s = summary(bundle);
  document.title = `${bundle.run.id} | GEAR / LAB`;
  $('run-title').textContent = bundle.run.title; $('run-id').textContent = bundle.run.id; $('spec-version').textContent = bundle.run.specVersion ? `v${bundle.run.specVersion}` : '—';
  $('run-description').textContent = bundle.run.id.startsWith('FLG-002') ? '固定式・単輪' : 'CADアセンブリ';
  $('model-name').textContent = `MODEL ${bundle.run.model || '—'}`; $('score').textContent = e.score == null ? '—' : number(e.score); $('score-max').textContent = `/ ${e.maxScore}`;
  $('score-note').textContent = e.score === null ? '未採点' : reviewNames[e.status];
  $('gate-count').textContent = s.total ? s.passed : '—'; $('gate-total').textContent = `/ ${s.total || '—'}`; $('gate-note').textContent = !s.total ? '評価ゲート未登録' : s.failed ? `${s.failed}項目 Fail` : s.passed === s.total ? '全ゲート Pass（入力値）' : `${s.total - s.passed}項目 未完了`;
  $('part-count').textContent = s.parts || '—'; $('triangle-count').textContent = s.parts ? `${number(s.triangles)} triangles` : 'CAD未読込';
  $('readiness').textContent = s.ready ? '基準達成（入力値）' : s.failed ? '未達成' : '評価待ち'; $('readiness').style.color = s.ready ? '#1d947a' : s.failed ? '#b45f53' : '';
  const status = $('review-status'); status.textContent = e.status === 'verified' ? '検証結果 読込済み' : e.status === 'self-reported' ? '自己申告 結果' : s.parts ? 'CAD読込・未検証' : '結果待ち'; status.className = `badge ${s.failed ? 'red' : e.status === 'verified' ? 'teal' : 'amber'}`;
  $('evidence-note').textContent = e.source || '評価JSONの入力値を表示しています。根拠ファイルと照合してください。'; $('evaluation-kind').textContent = reviewNames[e.status];
  $('gates').replaceChildren(...e.gates.map(g => {
    const row = node('div', null, 'gate'); const content = node('div'); content.append(node('strong', g.label), node('p', g.detail || '根拠未登録'));
    row.append(node('span', g.id, 'gate-id'), content, node('span', statusNames[g.status], `gate-status ${g.status}`)); return row;
  }));
  $('csv-count').textContent = csvFiles.length + (bundle.timeseries ? 1 : 0);
}
function renderOverview() {
  const target = $('tab-content'), e = bundle.evaluation; target.replaceChildren();
  if (e.metrics.length) {
    const metrics = node('div', null, 'metrics');
    for (const m of e.metrics) { const item = node('div', null, 'metric'), value = node('strong', m.value == null ? '—' : typeof m.value === 'number' ? number(m.value) : m.value); value.append(node('span', m.unit || '', 'unit')); item.append(node('span', m.label), value, node('small', m.source || '出典未登録')); metrics.append(item); }
    target.append(metrics);
  } else target.append(emptyResult('ベンチマークの実測・計算結果は、まだ読み込まれていません。', 'FreeCAD書出しJSONと評価JSONを読み込んでください。loads_and_margins.csv、requirements.csv、時刻歴CSVも併せて確認できます。'));
  if (e.categories?.length) {
    const scores = node('div', null, 'score-breakdown');
    for (const c of e.categories) {
      const row = node('div', null, 'score-row'), track = node('div', null, 'score-track'), fill = node('span'); fill.style.width = `${c.score == null ? 0 : c.score / c.maxScore * 100}%`; track.append(fill);
      row.append(node('span', c.label), track, node('strong', `${c.score == null ? '—' : number(c.score)} / ${c.maxScore}`)); scores.append(row);
    }
    target.append(scores);
  }
  if (e.issues.length) { const issues = node('div', null, 'issue-list'); const ul = node('ul'); e.issues.forEach(i => ul.append(node('li', i))); issues.append(node('strong', '未解決事項 / ISSUES'), ul); target.append(issues); }
  target.append(node('p', `評価区分：${reviewNames[e.status]}。${e.source || '評価根拠は未登録です。'} 透過・断面・分解は表示操作であり、実際の部品可動やCADの変更を行いません。`, 'source-note'));
}
function tableFor(csv) {
  const outer = node('div', null, 'table-scroll'), table = node('table'), head = node('thead'), tr = node('tr');
  csv.headers.forEach(h => tr.append(node('th', h))); head.append(tr); const body = node('tbody');
  csv.rows.slice(0, 1000).forEach(r => { const tr = node('tr'); r.forEach(c => tr.append(node('td', c))); body.append(tr); });
  table.append(head, body); outer.append(table); return outer;
}
function drawChart(values, label, unit = '') {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); svg.setAttribute('viewBox', '0 0 1000 210'); svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', label); svg.classList.add('csv-chart');
  const el = (tag, attrs, text) => { const n = document.createElementNS(svg.namespaceURI, tag); for (const [key, val] of Object.entries(attrs)) n.setAttribute(key, val); if (text != null) n.textContent = text; svg.append(n); return n; };
  const xs = values.map(v => v[0]), ys = values.map(v => v[1]); let minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  if (maxX === minX) maxX = minX + 1; if (maxY === minY) { minY -= .5; maxY += .5; }
  const x = v => 80 + (v - minX) / (maxX - minX) * 890, y = v => 166 - (v - minY) / (maxY - minY) * 142;
  for (let i = 0; i <= 4; i++) { const v = minY + (maxY - minY) * i / 4; el('line', { x1: 80, x2: 970, y1: y(v), y2: y(v), stroke: '#e4ecf0' }); el('text', { x: 70, y: y(v) + 4, 'text-anchor': 'end', fill: '#92a5af', 'font-size': 10 }, number(v)); }
  el('polyline', { points: values.map(v => `${x(v[0])},${y(v[1])}`).join(' '), fill: 'none', stroke: '#1fa68d', 'stroke-width': 2 });
  el('text', { x: 80, y: 194, fill: '#91a4ae', 'font-size': 10 }, number(minX)); el('text', { x: 970, y: 194, 'text-anchor': 'end', fill: '#91a4ae', 'font-size': 10 }, number(maxX));
  el('text', { x: 10, y: 14, fill: '#718b99', 'font-size': 10 }, `${label}${unit ? ` [${unit}]` : ''}`); return svg;
}
function renderCSV() {
  const target = $('tab-content'); target.replaceChildren(); const options = [...csvFiles];
  if (bundle.timeseries) options.unshift({ name: bundle.timeseries.name, timeseries: bundle.timeseries });
  if (!options.length) { target.append(emptyResult('CSVと時刻歴を追加できます。', '計算結果や要求対応表を読み込むと、列名を保った表を表示します。数値列はグラフに切り替えられます。')); return; }
  const bar = node('div', null, 'csv-bar'), select = node('select'); select.setAttribute('aria-label', 'CSVファイル'); options.forEach((o, i) => { const op = node('option', o.name); op.value = i; select.append(op); });
  bar.append(select); const contents = node('div'); target.append(bar, contents);
  const draw = () => {
    while (bar.children.length > 1) bar.lastChild.remove(); contents.replaceChildren(); const data = options[select.value];
    if (data.timeseries) {
      for (const s of data.timeseries.series) if (s.values.length) { contents.append(drawChart(s.values.slice(0, 5000), s.name, s.unit), node('p', `横軸：${data.timeseries.xLabel || 'time'} [${data.timeseries.xUnit || 's'}] · ${s.values.length} points（表示は先頭5000点）`, 'chart-note')); }
      return;
    }
    const numerical = data.csv.headers.map((h, i) => ({ h, i })).filter(({ i }) => data.csv.rows.length && data.csv.rows.every(r => r[i].trim() !== '' && Number.isFinite(Number(r[i]))));
    if (numerical.length >= 2) {
      const xSelect = node('select'), ySelect = node('select'); xSelect.setAttribute('aria-label', 'グラフの横軸'); ySelect.setAttribute('aria-label', 'グラフの縦軸');
      for (const { h, i } of numerical) for (const s of [xSelect, ySelect]) { const op = node('option', h); op.value = i; s.append(op); }
      ySelect.selectedIndex = 1; const xl = node('label', 'X'), yl = node('label', 'Y'); xl.append(xSelect); yl.append(ySelect); bar.append(xl, yl);
      const chart = node('div'); contents.append(chart);
      const redraw = () => { chart.replaceChildren(drawChart(data.csv.rows.slice(0, 5000).map(r => [Number(r[xSelect.value]), Number(r[ySelect.value])]), `${data.csv.headers[ySelect.value]} / X: ${data.csv.headers[xSelect.value]}`)); };
      xSelect.addEventListener('change', redraw); ySelect.addEventListener('change', redraw); redraw();
    }
    bar.append(node('span', `${number(data.csv.rows.length)} rows · 表は先頭1000行 / グラフは先頭5000点`)); contents.append(tableFor(data.csv));
  };
  select.addEventListener('change', draw); draw();
}
function renderFiles() {
  const target = $('tab-content'); target.replaceChildren(node('p', '読込済みファイルはブラウザ内で保持します。再読込すると初期状態に戻ります。FCStd / STEP / PDFの内容を自動検証する機能はありません。', 'source-note'));
  const list = node('div', null, 'file-list');
  for (const f of attachedFiles) { const a = node('a', `↓ ${f.name}`, 'file-chip'); a.href = f.url; a.download = f.name; list.append(a); }
  const loaded = new Set(attachedFiles.map(f => f.name));
  for (const source of bundle.run.sourceFiles || []) if (!loaded.has(source)) list.append(node('span', source, 'file-chip'));
  target.append(list); target.append(node('p', `スキーマ：${SCHEMA} · 座標：mm / Z-up · Three.js r180（ローカル同梱）`, 'source-note'));
}
function renderTab() { activeTab === 'overview' ? renderOverview() : activeTab === 'csv' ? renderCSV() : renderFiles(); }
function setBundle(data) {
  bundle = validateBundle(data); ['wireframe', 'transparent', 'section'].forEach(id => { $(id).checked = false; }); $('explode').value = 0; $('section-position').value = 50;
  loadGeometry(); renderParts(); renderHeader(); renderTab();
}
function releaseAttachments() { objectUrls.forEach(url => URL.revokeObjectURL(url)); objectUrls = []; attachedFiles = []; csvFiles = []; }
function newSTLBundle(files) {
  const id = files[0].name.replace(/\.stl$/i, ''); return { schema: SCHEMA, run: { id, title: id, model: '未登録', status: 'unverified', sourceFiles: files.map(f => f.name) }, parts: [], evaluation: { status: 'unverified', score: null, maxScore: 100, gates: [], metrics: [], issues: [], source: 'STL形状のみ。ベンチマーク評価は未読込。' } };
}
async function importFiles(list) {
  const files = [...list]; if (!files.length) return;
  try {
    if (files.reduce((n, f) => n + f.size, 0) > 200 * 1024 * 1024) throw new Error('一度に読み込めるファイルは合計200MBまでです。');
    const jsonFiles = files.filter(f => /\.json$/i.test(f.name)), stls = files.filter(f => /\.stl$/i.test(f.name));
    const jsons = await Promise.all(jsonFiles.map(async f => ({ file: f, data: JSON.parse(await f.text()) })));
    const bundles = jsons.filter(({ data }) => data.schema === SCHEMA && Array.isArray(data.parts));
    const evaluations = jsons.filter(({ data }) => data.schema === SCHEMA && !Array.isArray(data.parts));
    if (bundles.length > 1 || evaluations.length > 1) throw new Error('一度に読み込めるCAD JSONと評価JSONは、それぞれ1ファイルです。');
    if (jsons.some(({ data }) => data.schema !== SCHEMA)) throw new Error(`JSONのschemaは ${SCHEMA} が必要です。`);
    if (bundles.length && stls.length) throw new Error('CAD JSONとSTLは別々に読み込んでください。評価JSONとCSVは同時に選択できます。');
    if (!bundles.length && !stls.length && !evaluations.length && !files.some(f => /\.(csv|md|pdf)$/i.test(f.name))) throw new Error('FreeCADの書出しJSON、STL、CSV、評価JSONを選択してください。FCStd / STEP はFreeCADで書き出してください。');
    let next = structuredClone(bundles[0]?.data || (stls.length ? newSTLBundle(stls) : bundle));
    for (const [i, file] of stls.entries()) {
      const geometry = new STLLoader().parse(await file.arrayBuffer()), pos = geometry.getAttribute('position');
      if (!pos || pos.count < 3) throw new Error(`${file.name}: STLの頂点を読み込めません。`);
      next.parts.push({ id: `stl-${i}`, name: file.name.replace(/\.stl$/i, ''), color: palette[i % palette.length], vertices: Array.from(pos.array), indices: geometry.index ? Array.from(geometry.index.array) : Array.from({ length: pos.count }, (_, i) => i), sourceObject: file.name }); geometry.dispose();
    }
    if (evaluations.length) {
      const e = evaluations[0].data; if (!e.run || e.run.id !== next.run.id) throw new Error('評価JSONのrun.idが現在のCADと一致しません。別試行の評価を混ぜないでください。');
      next.evaluation = e.evaluation; if (e.timeseries) next.timeseries = e.timeseries;
    }
    validateBundle(next);
    const csvs = await Promise.all(files.filter(f => /\.csv$/i.test(f.name)).map(async file => ({ name: file.name, csv: parseCSV(await file.text()) })));
    // All parsing finishes before changing the displayed run.
    if (bundles.length || stls.length) releaseAttachments();
    for (const f of csvs) { csvFiles = csvFiles.filter(c => c.name !== f.name); csvFiles.push(f); }
    for (const file of files) {
      for (const previous of attachedFiles.filter(f => f.name === file.name)) { URL.revokeObjectURL(previous.url); objectUrls = objectUrls.filter(url => url !== previous.url); }
      attachedFiles = attachedFiles.filter(f => f.name !== file.name);
      const url = URL.createObjectURL(file); objectUrls.push(url); attachedFiles.push({ name: file.name, url });
    }
    if (!Array.isArray(next.run.sourceFiles)) next.run.sourceFiles = [];
    next.run.sourceFiles = [...new Set([...next.run.sourceFiles, ...files.map(f => f.name)])];
    setBundle(next); $('import-dialog').close(); toast(`${files.length}ファイルを読み込みました。${next.parts.length}部品を表示します。`);
  } catch (error) { toast(`読込できませんでした：${error.message}`, true); }
  finally { $('file-input').value = ''; }
}

const openImport = () => $('import-dialog').showModal();
$('import-button').addEventListener('click', openImport); $('empty-import').addEventListener('click', openImport);
$('close-dialog').addEventListener('click', () => $('import-dialog').close());
$('import-dialog').addEventListener('click', e => { if (e.target === $('import-dialog')) { const r = e.target.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) e.target.close(); } });
$('dropzone').addEventListener('click', () => $('file-input').click()); $('dropzone').addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('file-input').click(); } });
$('file-input').addEventListener('change', e => importFiles(e.target.files));
for (const name of ['dragenter', 'dragover']) $('dropzone').addEventListener(name, e => { e.preventDefault(); $('dropzone').classList.add('dragging'); });
$('dropzone').addEventListener('dragleave', () => $('dropzone').classList.remove('dragging')); $('dropzone').addEventListener('drop', e => { e.preventDefault(); $('dropzone').classList.remove('dragging'); importFiles(e.dataTransfer.files); });
document.addEventListener('dragover', e => e.preventDefault()); document.addEventListener('drop', e => { e.preventDefault(); if (!e.target.closest('#dropzone')) importFiles(e.dataTransfer.files); });
$('reset-run').addEventListener('click', () => { releaseAttachments(); setBundle(structuredClone(initial)); $('import-dialog').close(); toast('初期状態に戻しました。'); });
$('views').addEventListener('click', e => { const b = e.target.closest('[data-view]'); if (b) setView(b.dataset.view); });
$('fit').addEventListener('click', () => setView(document.querySelector('[data-view].active')?.dataset.view));
document.addEventListener('keydown', e => { if (e.key.toLowerCase() === 'f' && !['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName) && !$('import-dialog').open) $('fit').click(); });
for (const id of ['wireframe', 'transparent', 'explode', 'section', 'section-axis', 'section-position']) $(id).addEventListener('input', updateDisplay);
$('show-all').addEventListener('click', () => { for (const mesh of meshes.values()) mesh.visible = true; document.querySelectorAll('.part-row input').forEach(c => { c.checked = true; }); updateVisibleCount(); render3D(); });
$('screenshot').addEventListener('click', () => { if (!renderer || !bundle.parts.length) return toast('CADを読み込んでからPNGを保存してください。'); render3D(); renderer.domElement.toBlob(blob => { if (blob) download(blob, `${bundle.run.id}-view.png`); }); });
document.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click', () => { activeTab = b.dataset.tab; document.querySelectorAll('[data-tab]').forEach(t => t.setAttribute('aria-selected', t === b)); $('tab-content').setAttribute('aria-labelledby', b.id); renderTab(); }));
$('download-bundle').addEventListener('click', () => { if (bundle) download(new Blob([JSON.stringify(bundle)], { type: 'application/json' }), `${bundle.run.id}-benchmark.json`); });
init3D();
try {
  const response = await fetch('./data/benchmark.json'); if (!response.ok) throw new Error(`HTTP ${response.status}`); initial = validateBundle(await response.json()); setBundle(structuredClone(initial));
} catch (error) { toast(`初期データの読込に失敗しました。start-viewer.cmdから起動してください。${error.message}`, true); }
