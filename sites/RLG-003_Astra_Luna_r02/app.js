import * as THREE from 'three';
import {OrbitControls} from './vendor/OrbitControls.js';
import {nearestFrame, validateAssembly, formatNumber as number, strokeBracket, validateStrokeHistory, historyStrokeAt} from './core.mjs';

const $ = id => document.getElementById(id);
const labels = {Gear:['Main gear','主脚'],Bay:['Wing/body bay','脚庫'],Doors:['Bay doors','ふた'],Fixture:['Fixture','取付治具'],Envelopes:['Growth envelopes','成長包絡'],FluidVolumes:['Gas & oil','ガス・油']};
const stateLabels = ['全伸長 / Deployed','MLM静止 / Static','MTOM静止 / Static','D1最大圧縮 / D1 peak','機械最大圧縮 / Full stroke','引込30° / Retraction','引込60° / Retraction','引込85° / Retraction','収納・扉開 / Stowed, open','収納・扉閉 / Stowed, closed','非常伸長終端 / Emergency end'];
let assembly, meshes = [], geometry = [], renderer, camera, controls, scene, currentFrame, selected = -1, playing = false, playTime = 0, lastTime = 0, direction = 1;
let axes, grid;
let suspensionFrames = [], dropHistories = new Map(), bumpMode = null, bumpClock = 0, lastBumpPaint = 0;
const layers = new Map(Object.keys(labels).map(g => [g, g === 'Gear']));
const raycaster = new THREE.Raycaster();
const clipPlane = new THREE.Plane();
const pointer = new THREE.Vector2();

function showTab(id) {
  if (!$(id)?.classList.contains('tab-panel')) id = 'explorer';
  document.querySelectorAll('.tab-panel').forEach(el => el.classList.toggle('active', el.id === id));
  document.querySelectorAll('[data-tab]').forEach(el => { const active = el.dataset.tab === id; el.classList.toggle('active', active); el.setAttribute('aria-pressed', String(active)); });
  if (id !== 'explorer') stopAllPlayback();
  history.replaceState(null, '', `#${id}`);
  resize();
}
document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => showTab(button.dataset.tab)));
document.querySelectorAll('[data-go]').forEach(button => button.addEventListener('click', () => {showTab(button.dataset.go); $('workspace').scrollIntoView({behavior:'smooth'});}));
window.addEventListener('hashchange', () => showTab(location.hash.slice(1)));

async function fetchFile(url, type = 'json') {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  return type === 'buffer' ? response.arrayBuffer() : response.json();
}

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function setupScene() {
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(36, 1, 10, 100000);
  camera.up.set(0, 0, 1);
  renderer = new THREE.WebGLRenderer({antialias:true, alpha:true});
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.setClearColor(0x101c27, 0);
  renderer.localClippingEnabled = true;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.25;
  renderer.domElement.setAttribute('aria-label', 'RLG-003 CAD 3D model');
  renderer.domElement.tabIndex = 0;
  $('viewport').prepend(renderer.domElement);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = .09;
  controls.minDistance = 80;
  controls.maxDistance = 45000;
  controls.listenToKeyEvents(renderer.domElement);
  renderer.domElement.addEventListener('keydown', event => {
    const view = {f:'fit','+':'zoom-in','=':'zoom-in','-':'zoom-out'}[event.key.toLowerCase()];
    if (view) {event.preventDefault();cameraView(view);}
  });
  scene.add(new THREE.HemisphereLight(0xd9eafb, 0x586665, 2.8));
  for (const [color, intensity, position] of [[0xffffff,3.5,[4000,3000,7000]],[0x99bfee,2,[-4000,-5000,2000]],[0xb8f1db,1.5,[1000,-2000,-2000]]]) {
    const light = new THREE.DirectionalLight(color, intensity);
    light.position.set(...position); scene.add(light);
  }
  grid = new THREE.GridHelper(14000, 28, 0x466673, 0x2a414d);
  grid.rotation.x = Math.PI / 2; grid.position.z = -3500; grid.material.transparent = true; grid.material.opacity = .32; scene.add(grid);
  axes = new THREE.AxesHelper(1400); axes.visible = false; scene.add(axes);
  let down = null;
  renderer.domElement.addEventListener('pointerdown', event => { down = [event.clientX, event.clientY]; });
  renderer.domElement.addEventListener('pointerup', event => {
    if (!down || event.button !== 0 || Math.hypot(event.clientX-down[0], event.clientY-down[1]) > 5) return;
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.set((event.clientX-rect.left)/rect.width*2-1, -(event.clientY-rect.top)/rect.height*2+1);
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObjects(meshes.filter(mesh => mesh.visible)).filter(hit => !$('section').checked || clipPlane.distanceToPoint(hit.point) >= 0);
    selectPart(hits.length ? hits[0].object.userData.partIndex : -1);
  });
  controls.addEventListener('change', render);
  new ResizeObserver(resize).observe($('viewport'));
  requestAnimationFrame(tick);
}

function resize() {
  if (!renderer) return;
  const width = $('viewport').clientWidth, height = $('viewport').clientHeight;
  if (!width || !height) return;
  camera.aspect = width / height; camera.updateProjectionMatrix();
  renderer.setSize(width, height, false); render();
}
function render() { if (renderer) renderer.render(scene, camera); }

function loadGeometry(buffer) {
  geometry = assembly.meshes.map(info => {
    const positions = new Float32Array(buffer, info.position_offset, info.vertex_count * 3);
    const indices = new Uint32Array(buffer, info.index_offset, info.index_count);
    if (indices.some(i => i >= info.vertex_count) || positions.some(v => !Number.isFinite(v))) throw new Error('Invalid CAD triangles');
    const shape = new THREE.BufferGeometry();
    shape.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    shape.setIndex(new THREE.BufferAttribute(indices, 1));
    shape.computeVertexNormals(); shape.computeBoundingBox(); shape.computeBoundingSphere();
    return shape;
  });
  meshes = assembly.parts.map((part, i) => {
    const color = new THREE.Color().setRGB(part.color[0],part.color[1],part.color[2],THREE.SRGBColorSpace);
    const material = new THREE.MeshStandardMaterial({color, metalness:part.material === 'rubber' ? .02 : .38, roughness:part.material === 'rubber' ? .9 : .48, side:THREE.DoubleSide, clippingPlanes:[]});
    const mesh = new THREE.Mesh(geometry[assembly.states[0].parts[i].mesh], material);
    mesh.userData.partIndex = i;
    mesh.userData.center = new THREE.Vector3();
    scene.add(mesh); return mesh;
  });
}

function layerFor(part) {
  if (['gas','oil'].includes(part.material)) return 'FluidVolumes';
  if (part.id.endsWith('-ENVELOPE')) return 'Envelopes';
  return part.group;
}
function isOverlay(part) { return /-TYRE-CARCASS/.test(part.id); }

function applyFrame(frame) {
  currentFrame = frame;
  const explode = Number($('explode').value) * 5;
  frame.parts.forEach((pose, i) => {
    const mesh = meshes[i]; mesh.geometry = geometry[pose.mesh];
    mesh.position.set(...pose.position); mesh.quaternion.set(...pose.quaternion);
    if (explode) {
      const center = mesh.geometry.boundingSphere.center.clone().applyQuaternion(mesh.quaternion).add(mesh.position);
      // shortcut: radial display offsets only, use CAD constraints for an assembly sequence.
      const offset = center.sub(new THREE.Vector3(0, -700, -1000)).normalize().multiplyScalar(explode);
      mesh.position.add(offset);
    }
    mesh.updateMatrixWorld(true);
  });
  $('theta').replaceChildren(document.createTextNode(number(frame.theta_deg)), el('small','°'));
  $('stroke').replaceChildren(document.createTextNode(number(frame.stroke_mm)), el('small','mm'));
  $('beta').replaceChildren(document.createTextNode(number(frame.beta_deg)), el('small','°'));
  $('door').replaceChildren(document.createTextNode(number(frame.door_angle_deg,0)), el('small','°'));
  $('lock').textContent = frame.downlock >= .999 ? 'DOWN' : frame.uplock >= .999 ? 'UP' : 'RELEASED';
  const isSequence = Number.isFinite(frame.q);
  const isBump = frame.id === 'suspension';
  $('frame-type').textContent = isBump ? `s = ${number(frame.stroke_mm)} mm · visual blend` : isSequence ? `q = ${number(frame.q,2)} · CAD sample` : `${frame.id} · ${stateLabels[Number(frame.id.slice(1))]?.split(' / ')[0] ?? frame.label}`;
  $('state').value = isBump ? 'suspension' : isSequence ? 'sequence' : frame.id;
  $('bump-stroke').value = String(frame.stroke_mm);
  $('bump-value').textContent = `${number(frame.stroke_mm)} mm`;
  if (isSequence) {
    $('sequence').value = String(frame.q * 100);
    $('progress').replaceChildren(document.createTextNode(number(frame.q*100,0)),el('small','%'));
  } else {
    $('progress').replaceChildren(document.createTextNode('—'));
  }
  $('state-note').textContent = isBump ? 'S0〜S4のCAD姿勢を表示補間。タイヤ形状は全伸長時の形状に固定しています。' : isSequence ? '通常シーケンスのCADサンプル。扉角・ロック指令を含みます。' : frame.id === 'S10' ? '非常伸長後の静的CAD姿勢。非常伸長の動的成立を示すものではありません。' : frame.id === 'S9' ? '全収納・扉閉。静的包含と連続経路の隙間は別の検証です。' : '保存済みCADの検査姿勢。格納スライダーを動かすと通常シーケンスへ切り替わります。';
  updateAppearance();
}

function applySuspension(stroke, caption) {
  const leavingRetraction = currentFrame?.theta_deg > 0;
  const {lower,upper,ratio,value} = strokeBracket(suspensionFrames,stroke);
  const blend = key => lower[key]+(upper[key]-lower[key])*ratio;
  const parts = lower.parts.map((a,i) => {
    const b=upper.parts[i];
    return {
      // shortcut: changing tire topology is held at S0, add contact meshes for a contact simulation.
      mesh:assembly.parts[i].id.endsWith('-TYRE-CONTACT') ? suspensionFrames[0].parts[i].mesh : ratio<.5 ? a.mesh : b.mesh,
      position:a.position.map((value,j)=>value+(b.position[j]-value)*ratio),
      quaternion:new THREE.Quaternion(...a.quaternion).slerp(new THREE.Quaternion(...b.quaternion),ratio).toArray(),
    };
  });
  applyFrame({id:'suspension',parts,stroke_mm:value,theta_deg:0,beta_deg:blend('beta_deg'),door_angle_deg:180,downlock:1,uplock:0});
  if(leavingRetraction) cameraView('fit');
  $('bump-time').textContent = caption;
}

function enableBumpControls() {
  const ready = suspensionFrames.length === 5 && Boolean(renderer) && meshes.length === assembly?.parts.length;
  $('bump-stroke').disabled = $('bump-cycle').disabled = $('bump-quick').disabled = !ready;
  $('bump-case').disabled = $('bump-drop').disabled = !ready || !dropHistories.size;
}

function updateAppearance() {
  if (!assembly) return;
  const isolate = $('isolate').checked && selected >= 0;
  const xray = $('xray').checked;
  const normal = new THREE.Vector3(); normal[$('section-axis').value] = -1;
  clipPlane.set(normal, Number($('section-position').value));
  meshes.forEach((mesh, i) => {
    const part = assembly.parts[i], group = layerFor(part);
    const overlay = isOverlay(part);
    // Carcass and growth solids overlap the visible contact tire; keep them opt-in.
    mesh.visible = isolate ? i === selected : Boolean(layers.get(group)) && (!overlay || group === 'Envelopes' || group === 'FluidVolumes');
    if (i === selected) mesh.visible = true;
    const transparent = group === 'Bay' || group === 'Envelopes' || group === 'FluidVolumes' || (xray && i !== selected);
    mesh.material.transparent = transparent;
    mesh.material.opacity = transparent ? (group === 'Bay' ? .15 : group === 'Envelopes' ? .14 : .23) : 1;
    mesh.material.depthWrite = !transparent;
    mesh.material.emissive.setHex(i === selected ? 0x257f65 : 0x000000);
    mesh.material.emissiveIntensity = i === selected ? .65 : 0;
    mesh.material.clippingPlanes = $('section').checked ? [clipPlane] : [];
  });
  axes.visible = $('axes').checked;
  render();
}

function cameraView(view) {
  if (!meshes.length) return;
  if (view.startsWith('zoom-')) {
    const vector = camera.position.clone().sub(controls.target).multiplyScalar(view === 'zoom-in' ? .8 : 1.25);
    vector.clampLength(controls.minDistance, controls.maxDistance);
    camera.position.copy(controls.target).add(vector);controls.update();render();return;
  }
  const bounds = new THREE.Box3();
  meshes.filter(mesh => mesh.visible).forEach(mesh => bounds.expandByObject(mesh));
  if (bounds.isEmpty()) return;
  const center = bounds.getCenter(new THREE.Vector3());
  const size = bounds.getSize(new THREE.Vector3());
  const distance = Math.max(size.x, size.y, size.z) / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov/2))) * 1.25 / Math.min(camera.aspect, 1);
  const directions = {iso:[1.2,1.6,.8],front:[1,0,.01],side:[0,1,.01],top:[.001,0,1]};
  const vector = view === 'fit' ? camera.position.clone().sub(controls.target).normalize() : new THREE.Vector3(...(directions[view] ?? directions.iso)).normalize();
  camera.position.copy(center).addScaledVector(vector,distance);
  camera.up.set(0,0,1); controls.target.copy(center); controls.update(); render();
  document.querySelectorAll('[data-view]').forEach(button => button.classList.toggle('selected',button.dataset.view === view));
}
document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => cameraView(button.dataset.view)));

function selectPart(index) {
  selected = index;
  const container = $('selected-part'); container.replaceChildren(el('span','SELECTED PART','eyebrow'));
  if (index < 0) container.append(el('p','モデルまたはリストから部品を選択。'));
  else {
    const part = assembly.parts[index];
    container.append(el('p',part.id), el('p',part.label));
    const info = el('dl');
    for (const [key,value] of [['Material',part.material],['Mass',`${number(part.mass_kg,3)} kg`],['Group',part.group]]) info.append(el('dt',key),el('dd',value));
    container.append(info);
  }
  document.querySelectorAll('.part-item').forEach(button => button.classList.toggle('selected',Number(button.dataset.index) === index));
  updateAppearance();
}

function populateParts() {
  if (!assembly) return;
  const query = $('part-search').value.trim().toLowerCase();
  const fragment = document.createDocumentFragment();
  let count = 0;
  assembly.parts.forEach((part, index) => {
    if (query && !`${part.id} ${part.name} ${part.label} ${part.material}`.toLowerCase().includes(query)) return;
    count++;
    const button = el('button',part.id,'part-item'); button.dataset.index = index;
    button.title = `${part.id} · ${part.label}`;
    button.append(el('small',part.label));
    button.classList.toggle('selected',index === selected);
    button.addEventListener('click',() => selectPart(index)); fragment.append(button);
  });
  if (!count) fragment.append(el('p','一致する部品がありません。','fineprint'));
  $('part-list').replaceChildren(fragment); $('result-count').textContent = count;
}
$('part-search').addEventListener('input',populateParts);
$('clear-selection').addEventListener('click',() => selectPart(-1));
$('reset-layers').addEventListener('click',() => {
  for (const group of layers.keys()) layers.set(group,group === 'Gear');
  $('xray').checked = $('axes').checked = $('isolate').checked = $('section').checked = false;
  $('explode').value = 0; $('explode-value').textContent = '0%';
  document.querySelectorAll('[data-layer]').forEach(input => {input.checked = layers.get(input.dataset.layer);});
  selected = -1; selectPart(-1); if(currentFrame) applyFrame(currentFrame);
});
['xray','axes','isolate','section','section-axis'].forEach(id => $(id).addEventListener('change',updateAppearance));
$('section-position').addEventListener('input',() => {$('section-value').textContent = `${$('section-position').value} mm`;updateAppearance();});
$('explode').addEventListener('input',() => {$('explode-value').textContent = `${$('explode').value}%`;if(currentFrame)applyFrame(currentFrame);});
$('state').addEventListener('change',() => {stopAllPlayback();if($('state').value==='suspension'){applySuspension(Number($('bump-stroke').value),'Manual / 手動');return;}const frame = assembly.states.find(frame => frame.id === $('state').value);applyFrame(frame ?? nearestFrame(assembly.sequence,Number($('sequence').value)/100));});
$('sequence').addEventListener('input',() => {stopAllPlayback();applyFrame(nearestFrame(assembly.sequence,Number($('sequence').value)/100));});
$('bump-stroke').addEventListener('input',()=>{stopAllPlayback();applySuspension(Number($('bump-stroke').value),'Manual / 手動');});

function stopPlayback() { playing = false; $('play').textContent = '▶'; $('play').setAttribute('aria-label','格納動作を再生'); }
function stopBumpPlayback() {bumpMode=null;$('bump-cycle').textContent='↕ Cycle / 往復';$('bump-drop').textContent='▶ Drop / 着陸再生';$('bump-quick').textContent='↕';$('bump-quick').classList.remove('selected');$('bump-quick').setAttribute('aria-label','上下動を再生');}
function stopAllPlayback() {stopPlayback();stopBumpPlayback();}
$('play').addEventListener('click',() => {
  if (playing) {stopPlayback();return;}
  stopBumpPlayback();
  playTime = Number.isFinite(currentFrame?.q) ? currentFrame.q : 0;
  if (playTime >= 1) direction = -1; else if(playTime <= 0) direction = 1;
  playing = true; $('play').textContent = 'Ⅱ'; $('play').setAttribute('aria-label','格納動作を停止');
});
function toggleCycle() {
  if(bumpMode==='cycle'){stopBumpPlayback();return;}
  stopAllPlayback();bumpMode='cycle';bumpClock=0;
  $('bump-cycle').textContent='Ⅱ Stop cycle / 停止';
  $('bump-quick').textContent='Ⅱ';$('bump-quick').classList.add('selected');$('bump-quick').setAttribute('aria-label','上下動を停止');
  applySuspension(0,'Cycle / 表示往復');
}
$('bump-cycle').addEventListener('click',toggleCycle);
$('bump-quick').addEventListener('click',()=>{if(bumpMode){stopBumpPlayback();return;}toggleCycle();});
$('bump-drop').addEventListener('click',()=>{
  if(bumpMode==='drop'){stopBumpPlayback();return;}
  stopAllPlayback();bumpMode='drop';bumpClock=0;
  $('bump-drop').textContent='Ⅱ Stop replay / 停止';
  $('bump-quick').textContent='Ⅱ';$('bump-quick').classList.add('selected');$('bump-quick').setAttribute('aria-label','上下動を停止');
  applySuspension(0,`${$('bump-case').value} · t = 0.000 s`);
});
function tick(time) {
  const dt = Math.min((time - lastTime)/1000,.1); lastTime = time;
  if (playing && assembly && !document.hidden) {
    playTime += dt * direction / 14;
    if (playTime >= 1 || playTime <= 0) {playTime = Math.max(0,Math.min(1,playTime));direction *= -1;}
    const frame = nearestFrame(assembly.sequence,playTime);
    if (frame !== currentFrame) applyFrame(frame);
  }
  if(bumpMode && !document.hidden) {
    bumpClock += dt*(bumpMode==='drop'?Number($('bump-speed').value):1);
    if(time-lastBumpPaint>=1000/30) {
      lastBumpPaint=time;
      if(bumpMode==='cycle') {
        bumpClock%=5;
        applySuspension(300*(1-Math.cos(bumpClock*2*Math.PI/5)),'Cycle / 表示往復');
      } else {
        const points=dropHistories.get($('bump-case').value), end=points.at(-1).t_s;
        const elapsed=Math.min(bumpClock,end), done=bumpClock>=end;
        applySuspension(historyStrokeAt(points,elapsed),`${$('bump-case').value} · t = ${number(elapsed,3)} / ${number(end,3)} s${done?' · complete':''}`);
        if(done)stopBumpPlayback();
      }
    }
  }
  controls?.update();
  requestAnimationFrame(tick);
}

async function loadModel() {
  try {
    const [data,buffer] = await Promise.all([fetchFile('./model/assembly.json'),fetchFile('./model/geometry.bin','buffer')]);
    assembly = validateAssembly(data,buffer.byteLength);
    suspensionFrames = assembly.states.filter(frame=>/^S[0-4]$/.test(frame.id)).sort((a,b)=>a.stroke_mm-b.stroke_mm);
    if(suspensionFrames.length!==5 || suspensionFrames.some(frame=>!Number.isFinite(frame.stroke_mm))) throw new Error('Missing suspension CAD samples');
    setupScene(); loadGeometry(buffer);
    $('part-count').textContent = assembly.parts.length;
    $('mesh-status').textContent = `${assembly.parts.length} PARTS / ${assembly.sequence.length} SAMPLES`;
    for (const [group, [english,japanese]] of Object.entries(labels)) {
      const count = assembly.parts.filter(part => layerFor(part) === group).length;
      if (!count) continue;
      const row = el('div',undefined,'layer-row');
      const label = el('label',english); label.append(el('small',`${japanese} · ${count}`));
      const input = el('input'); input.type = 'checkbox'; input.checked = layers.get(group);input.dataset.layer = group;input.id = `layer-${group}`;label.htmlFor = input.id;
      input.addEventListener('change',() => {layers.set(group,input.checked);updateAppearance();});
      row.append(label,input); $('layers').append(row);
    }
    $('state').replaceChildren(...assembly.states.map(frame => {const option = el('option',`${frame.id} · ${stateLabels[Number(frame.id.slice(1))] ?? frame.label}`);option.value=frame.id;return option;}));
    const option = el('option','q · 通常シーケンス / Sequence'); option.value = 'sequence'; $('state').append(option);
    const bumpOption=el('option','s · 上下動 / Visual interpolation');bumpOption.value='suspension';$('state').append(bumpOption);
    applyFrame(assembly.states[0]); populateParts(); resize(); cameraView('iso');
    ['state','sequence','play'].forEach(id => {$(id).disabled = false;});
    enableBumpControls();
    const p = $('provenance'); p.textContent = `CAD SHA-256: ${assembly.source_sha256} · Units: mm · ${assembly.parts.length} parts · ${assembly.sequence.length} sequence samples`;
  } catch (error) {
    console.error(error);
    $('mesh-status').textContent = 'VIEWER UNAVAILABLE';
    const box = $('load-error');box.hidden = false;box.replaceChildren(el('strong','3Dモデルを読み込めませんでした。'),el('p',location.protocol === 'file:' ? 'フォルダをHTTPサーバーで開いてください。READMEに起動方法があります。' : 'WebGL2の対応・有効化と、model/・vendor/フォルダの配置を確認してください。'));
    const link = el('a','PDF図面を開く ↗');link.href = './downloads/drawings.pdf';box.append(link);
  }
}

function table(container, headers, rows) {
  const node = el('table'), head = el('thead'), tr = el('tr');
  for (const title of headers) tr.append(el('th',title));head.append(tr);node.append(head);
  const body = el('tbody');
  for (const row of rows) {const tr = el('tr');for (const value of row) {const td = el('td');if(value instanceof Node)td.append(value);else td.textContent=value;tr.append(td);}body.append(tr);}
  if (!rows.length) {const row=el('tr'),cell=el('td','該当する記録がありません。');cell.colSpan=headers.length;row.append(cell);body.append(row);}
  node.append(body); container.replaceChildren(node);
}
function badge(status) {return el('span',status,`badge ${status === 'Pass' ? 'pass' : ['Fail','Rejected'].includes(status) ? 'fail' : 'pending'}`);}

function drawHistory(report) {
  const points = report.history.filter(point => point.case_id === $('chart-case').value);
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 1000 290');svg.setAttribute('role','img');svg.setAttribute('aria-label',`${$('chart-case').value} ストローク時刻歴。横軸 時間s、縦軸 ストロークmm。`);
  if (!points.length) {$('history-chart').replaceChildren(el('p','時刻歴データがありません。'));return;}
  const maxTime = Math.max(...points.map(p => p.t_s),.001), maxStroke = Math.max(600,...points.map(p => p.stroke_mm));
  function svgEl(tag, attributes, text) {const n=document.createElementNS(ns,tag);for(const [key,value]of Object.entries(attributes))n.setAttribute(key,String(value));if(text!==undefined)n.textContent=text;svg.append(n);return n;}
  for(let i=0;i<=4;i++) {
    const y=22+i*53;
    svgEl('line',{x1:65,y1:y,x2:970,y2:y,stroke:'#e2e8e1','stroke-width':1});
    svgEl('text',{x:53,y:y+4,'text-anchor':'end',class:'chart-label'},number(maxStroke*(1-i/4),0));
    svgEl('text',{x:65+i*226.25,y:260,'text-anchor':'middle',class:'chart-label'},number(maxTime*i/4,2));
  }
  svgEl('text',{x:65,y:12,class:'chart-label'},'STROKE / mm');svgEl('text',{x:970,y:285,'text-anchor':'end',class:'chart-label'},'TIME / s');
  const path = points.map((point,i) => `${i?'L':'M'}${(65+point.t_s/maxTime*905).toFixed(2)},${(234-point.stroke_mm/maxStroke*212).toFixed(2)}`).join(' ');
  svgEl('path',{d:path,fill:'none',stroke:'#247960','stroke-width':2.5,'stroke-linejoin':'round'});
  $('history-chart').replaceChildren(svg);
}

async function loadReport() {
  try {
    const report = await fetchFile('./data/report.json');
    const mtom = report.static.find(row => row.case_id === 'L0T');
    const d1 = report.dynamic.find(row => row.case_id === 'D1');
    const metrics = [ ['DRY MASS / 乾燥質量',number(report.mass.dry_mass_kg/1000,2),'t','6 tは参考目標。必達条件ではありません。'],['MTOM SAG / 静沈下',number(mtom?.percent_stroke,2),'%','元45%上限: NG · 承認済み47%上限: Pass'],['D1 PEAK / 最大ストローク',number(d1?.max_stroke_m*1000,1),'mm','機械最大600 mm · 自実装の時刻積分'],['OPERATING MASS / 作動質量',number(report.mass.operating_mass_kg/1000,2),'t','オレオ油を含む。脚庫・ふたの仮想質量を除外。'] ];
    for(const [title,value,unit,note]of metrics){const card=el('article',undefined,'metric'),strong=el('strong',value);strong.append(el('small',unit));card.append(el('span',title),strong,el('p',note));$('metrics').append(card);}
    table($('dynamic-table'),['CASE','Stroke mm','Reaction MN','Pressure MPa abs','Energy residual %','Tire margin mm'],report.dynamic.map(row=>[row.case_id,number(row.max_stroke_m*1000),number(row.max_ground_reaction_n/1e6,3),number(row.pressure_max_abs_pa/1e6,2),number(row.energy_residual_pct,3),number(row.tire_bottom_margin_m*1000,2)]));
    table($('structure-table'),['PART / CASE','MODE','YIELD MARGIN','BASIS'],report.structural.filter(row=>Number(row.yield_margin)<0).map(row=>[`${row.item} / ${row.case_id??'comparison'}`,row.mode,el('span',number(row.yield_margin,3),'negative'),row.basis]));
    table($('brake-table'),['CASE','Energy / brake MJ','Final °C','Thermal margin °C'],report.brakes.map(row=>[row.scenario,number(row.energy_per_brake_j/1e6,2),number(row.final_temperature_c,0),number(row.thermal_margin_c,0)]));
    const cases = [...new Set(report.history.map(row=>row.case_id))];
    dropHistories = new Map(cases.map(id=>[id,validateStrokeHistory(report.history.filter(row=>row.case_id===id))]));
    $('bump-case').replaceChildren(...cases.map(id=>{const o=el('option',id);o.value=id;return o;}));
    $('chart-case').replaceChildren(...cases.map(id=>{const o=el('option',id);o.value=id;return o;}));
    $('chart-case').addEventListener('change',()=>{$('bump-case').value=$('chart-case').value;drawHistory(report);});drawHistory(report);
    $('bump-case').addEventListener('change',()=>{stopBumpPlayback();$('chart-case').value=$('bump-case').value;drawHistory(report);$('bump-time').textContent='Ready / 再生待ち';});
    enableBumpControls();
    const counts = ['Pass','Fail','Pending'].map(status => [status,report.requirements.filter(row=>row.status === status).length]);
    $('requirement-counts').replaceChildren(...counts.map(([status,count])=>el('span',`${status} · ${count}`)));
    const showRequirements = () => {
      const rows=report.requirements.filter(row=>$('requirement-filter').value === 'all'||row.status === $('requirement-filter').value);
      table($('requirement-table'),['ID','STATUS','REQUIREMENT / 要求','EVIDENCE / 証拠','NOTES / 留意点'],rows.map(row=>[row.requirement_id,badge(row.status),el('span',row.requirement,'long-cell'),row.evidence,el('span',row.notes,'long-cell')]));
    };
    $('requirement-filter').addEventListener('change',showRequirements);showRequirements();
    for(const item of report.images) {
      const figure=el('figure',undefined,'image-card'),a=el('a');a.href=item.src;a.target='_blank';a.rel='noopener';
      const image=el('img');image.src=item.src;image.alt=item.title;image.loading='lazy';a.append(image);
      const caption=el('figcaption',item.title);caption.append(el('span',item.caption));figure.append(a,caption);$('image-gallery').append(figure);
    }
    for(const item of report.failures) {
      const article=el('article',undefined,'failure-card'),a=el('a');a.href=item.src;a.target='_blank';a.rel='noopener';
      const image=el('img');image.src=item.src;image.alt=item.title;image.loading='lazy';a.append(image);
      const text=el('div',undefined,'failure-text');text.append(badge(item.status??'Fail'),el('h3',item.title),el('p',item.caption));article.append(a,text);$('failure-gallery').append(article);
    }
    for(const item of report.downloads) {
      const a=el('a',undefined,'download-card');a.href=item.href;a.download='';const label=el('div');label.append(el('strong',item.name),el('small',item.description));a.append(label,el('span',`${number(item.bytes/1024,0)} KB ↓`));$('download-list').append(a);
    }
  } catch(error) {
    console.error(error);
    for(const id of ['metrics','requirement-table','download-list']) $(id).replaceChildren(el('p','記録データを読み込めませんでした。data/report.json の配置を確認してください。','negative'));
  }
}

showTab(location.hash.slice(1) || 'explorer');
await Promise.allSettled([loadModel(),loadReport()]);
