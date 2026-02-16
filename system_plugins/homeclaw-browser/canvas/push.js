/**
 * Push canvas updates to connected WebSocket clients subscribed by session key.
 */

const clients = new Map(); // sessionKey -> Set<WebSocket>

function subscribe(sessionKeyStr, ws) {
  if (!clients.has(sessionKeyStr)) clients.set(sessionKeyStr, new Set());
  clients.get(sessionKeyStr).add(ws);
  ws.on('close', () => {
    const set = clients.get(sessionKeyStr);
    if (set) {
      set.delete(ws);
      if (set.size === 0) clients.delete(sessionKeyStr);
    }
  });
}

function push(sessionKeyStr, document) {
  const set = clients.get(sessionKeyStr);
  if (!set) return;
  const payload = JSON.stringify({ type: 'canvas_update', document });
  for (const ws of set) {
    if (ws.readyState === 1) {
      try {
        ws.send(payload);
      } catch (e) {
        set.delete(ws);
      }
    }
  }
}

module.exports = { subscribe, push };
