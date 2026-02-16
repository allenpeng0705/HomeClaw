/**
 * Send a command to a registered node and wait for response (with timeout).
 */

const registry = require('./registry');

const CMD_TIMEOUT_MS = 10000;
const pending = new Map(); // id -> { resolve, reject, timer }

function normalizeResult(msg) {
  const payload = msg.payload;
  if (payload && typeof payload === 'object' && ('success' in payload || 'text' in payload || 'error' in payload)) {
    return { success: payload.success !== false, text: payload.text != null ? String(payload.text) : '', error: payload.error || null };
  }
  if (typeof payload === 'string') return { success: true, text: payload, error: null };
  return { success: msg.ok !== false, text: payload != null ? JSON.stringify(payload) : '', error: msg.error || null };
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
        resolve({ success: false, text: '', error: 'Command timeout' });
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
