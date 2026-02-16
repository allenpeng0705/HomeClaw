/**
 * In-memory canvas document store per session key.
 * Document shape: { title?: string, blocks: Array<{ type, content?, label?, id? }> }
 */

const store = new Map();

function sessionKey(params = {}, userId = '') {
  const sid = (params.session_id || params.sessionId || '').trim();
  const uid = (userId || '').trim();
  return sid || uid || 'default';
}

function set(sessionKeyStr, document) {
  const doc = typeof document === 'string' ? { title: '', blocks: [{ type: 'text', content: document }] } : document;
  store.set(sessionKeyStr, {
    ...doc,
    title: doc.title != null ? doc.title : '',
    blocks: Array.isArray(doc.blocks) ? doc.blocks : [],
    updatedAt: Date.now(),
  });
  return store.get(sessionKeyStr);
}

function get(sessionKeyStr) {
  return store.get(sessionKeyStr) || null;
}

function getAll() {
  const out = {};
  for (const [k, v] of store) {
    out[k] = v;
  }
  return out;
}

module.exports = {
  sessionKey,
  set,
  get,
  getAll,
};
