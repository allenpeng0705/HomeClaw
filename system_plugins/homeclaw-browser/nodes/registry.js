/**
 * Registry of connected nodes (WebSocket clients that registered with role: node).
 * Each node has node_id and capabilities (e.g. canvas, camera, screen, location).
 */

const nodes = new Map(); // node_id -> { ws, capabilities, registeredAt }

function register(nodeId, ws, capabilities = []) {
  const list = Array.isArray(capabilities) ? capabilities : [capabilities];
  nodes.set(nodeId, { ws, capabilities: list, registeredAt: Date.now() });
  ws.on('close', () => nodes.delete(nodeId));
}

function get(nodeId) {
  return nodes.get(nodeId) || null;
}

function list() {
  return Array.from(nodes.entries()).map(([id, v]) => ({
    node_id: id,
    capabilities: v.capabilities,
    registeredAt: v.registeredAt,
  }));
}

function unregister(nodeId) {
  const n = nodes.get(nodeId);
  if (n && n.ws) n.ws.close();
  nodes.delete(nodeId);
}

module.exports = { register, get, list, unregister };
