/**
 * Send a command to a registered node and wait for response (with timeout).
 * Use a long timeout so media commands (camera_clip, camera_snap, screen_record) have time to
 * acquire device, record, encode, and return (e.g. 3s clip + permissions + encoding can exceed 10s).
 */

const registry = require('./registry');

const CMD_TIMEOUT_MS = 300000;  // 5 min: video/photo/screen_record need time for device + encode + reply (match Core plugin timeout)
const pending = new Map(); // id -> { resolve, reject, timer }

function normalizeResult(msg) {
  const payload = msg.payload;
  const base = { success: true, text: '', error: null, media: null };
  if (payload && typeof payload === 'object' && ('success' in payload || 'text' in payload || 'error' in payload)) {
    base.success = payload.success !== false;
    base.text = payload.text != null ? String(payload.text) : '';
    base.error = payload.error || null;
    if (payload.media != null && typeof payload.media === 'string') base.media = payload.media;
    return base;
  }
  if (typeof payload === 'string') return { ...base, text: payload };
  return { ...base, success: msg.ok !== false, text: payload != null ? JSON.stringify(payload) : '', error: msg.error || null };
}

function handleNodeMessage(nodeId, data) {
  let msg;
  try {
    msg = typeof data === 'string' ? JSON.parse(data) : data;
  } catch (e) {
    return;
  }
  if ((msg.type === 'command_result' || msg.type === 'res') && msg.id != null) {
    const p = pending.get(String(msg.id));
    if (p) {
      clearTimeout(p.timer);
      pending.delete(String(msg.id));
      p.resolve(normalizeResult(msg));
    }
  }
}

async function sendCommand(nodeId, command, params = {}) {
  const node = registry.get(nodeId);
  if (!node || !node.ws || node.ws.readyState !== 1) {
    return { success: false, text: `Node '${nodeId}' not connected`, error: null };
  }
  const id = `cmd_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      if (pending.has(id)) {
        pending.delete(id);
        resolve({
          success: false,
          text: '',
          error: `Command timeout (${nodeId} did not respond in time). Ensure the Nodes page is open, the device is connected, and for camera/video grant camera and microphone permission.`,
        });
      }
    }, CMD_TIMEOUT_MS);
    pending.set(id, { resolve: (v) => resolve(v), timer });

    try {
      node.ws.send(JSON.stringify({ type: 'command', id, command, params }));
    } catch (e) {
      clearTimeout(timer);
      pending.delete(id);
      resolve({ success: false, text: '', error: String(e.message) });
    }
  });
}

module.exports = { sendCommand, handleNodeMessage };
