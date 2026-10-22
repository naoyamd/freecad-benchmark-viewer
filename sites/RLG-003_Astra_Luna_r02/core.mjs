export function nearestFrame(frames, progress) {
  if (!frames.length || !Number.isFinite(progress)) throw new Error('Invalid sequence');
  return frames.reduce((best, frame) => Math.abs(frame.q - progress) < Math.abs(best.q - progress) ? frame : best);
}

export function validateAssembly(data, byteLength) {
  if (data.schema !== 1 || data.units !== 'mm' || !data.parts?.length || !data.meshes?.length) throw new Error('Unsupported CAD export');
  if (!data.states?.length || !data.sequence?.length) throw new Error('Missing CAD states');
  for (const mesh of data.meshes) {
    for (const key of ['position_offset', 'vertex_count', 'index_offset', 'index_count']) {
      if (!Number.isSafeInteger(mesh[key]) || mesh[key] < 0) throw new Error('Invalid mesh range');
    }
    if (!mesh.vertex_count || !mesh.index_count || mesh.index_count % 3 || mesh.position_offset % 4 || mesh.index_offset % 4 || mesh.position_offset + mesh.vertex_count * 12 > byteLength || mesh.index_offset + mesh.index_count * 4 > byteLength) throw new Error('Truncated mesh buffer');
  }
  if (new Set(data.parts.map(p => p.id)).size !== data.parts.length) throw new Error('Duplicate part ID');
  for (const frame of [...data.states, ...data.sequence]) {
    if (frame.parts.length !== data.parts.length) throw new Error('Incomplete CAD frame');
    for (const part of frame.parts) {
      if (!Number.isInteger(part.mesh) || !data.meshes[part.mesh] || part.position.length !== 3 || part.quaternion.length !== 4 || ![...part.position, ...part.quaternion].every(Number.isFinite)) throw new Error('Invalid part transform');
      if (Math.abs(part.quaternion.reduce((sum,v) => sum + v*v,0) - 1) > 1e-4) throw new Error('Invalid quaternion');
    }
  }
  if (data.sequence.some((frame, i) => !Number.isFinite(frame.q) || frame.q < 0 || frame.q > 1 || (i && frame.q <= data.sequence[i - 1].q))) throw new Error('Invalid sequence order');
  if (data.sequence[0].q !== 0 || data.sequence.at(-1).q !== 1) throw new Error('Missing sequence endpoints');
  return data;
}

export function formatNumber(value, digits = 1) {
  return Number.isFinite(Number(value)) ? Number(value).toLocaleString('en-US', {minimumFractionDigits: digits, maximumFractionDigits: digits}) : '—';
}

export function strokeBracket(frames, stroke) {
  if (!frames.length || !Number.isFinite(stroke)) throw new Error('Invalid suspension stroke');
  const value = Math.max(frames[0].stroke_mm, Math.min(frames.at(-1).stroke_mm, stroke));
  const right = frames.findIndex(frame => frame.stroke_mm >= value);
  if (right <= 0) return {lower:frames[0],upper:frames[0],ratio:0,value};
  const lower = frames[right-1], upper = frames[right];
  return {lower,upper,ratio:(value-lower.stroke_mm)/(upper.stroke_mm-lower.stroke_mm),value};
}

export function validateStrokeHistory(points) {
  if (points.length < 2 || points.some((point,i) => !Number.isFinite(point.t_s) || !Number.isFinite(point.stroke_mm) || (i && point.t_s <= points[i-1].t_s))) throw new Error('Invalid stroke history');
  return points;
}

export function historyStrokeAt(points, time) {
  if (!points.length || !Number.isFinite(time)) throw new Error('Invalid playback time');
  if (time <= points[0].t_s) return points[0].stroke_mm;
  if (time >= points.at(-1).t_s) return points.at(-1).stroke_mm;
  const right = points.findIndex(point => point.t_s >= time);
  const a=points[right-1], b=points[right], ratio=(time-a.t_s)/(b.t_s-a.t_s);
  return a.stroke_mm+(b.stroke_mm-a.stroke_mm)*ratio;
}
