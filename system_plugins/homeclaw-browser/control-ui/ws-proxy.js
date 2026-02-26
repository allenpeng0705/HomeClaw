/**
 * Control UI WebSocket proxy: browser client <-> Core /ws.
 * Export create(options) -> { handleUpgrade(request, socket, head) } for /ws only.
 */
const { WebSocketServer, WebSocket } = require('ws');

/**
 * @param {{ CORE_WS_URL: string; CORE_API_KEY?: string }} options
 * @returns {{ handleUpgrade(request, socket, head): void }}
 */
function create(options) {
  const { CORE_WS_URL, CORE_API_KEY = '' } = options;
  const chatWss = new WebSocketServer({ noServer: true });

  function handleUpgrade(request, socket, head) {
    chatWss.handleUpgrade(request, socket, head, (clientWs) => {
      let coreWsUrl = CORE_WS_URL;
      const headers = {};
      try {
        const u = new URL((request.url || '/ws'), 'http://x');
        const clientApiKey = u.searchParams.get('api_key') || u.searchParams.get('x-api-key');
        if (clientApiKey) {
          coreWsUrl += (coreWsUrl.includes('?') ? '&' : '?') + 'api_key=' + encodeURIComponent(clientApiKey);
        } else if (CORE_API_KEY) {
          headers['X-API-Key'] = CORE_API_KEY;
        }
      } catch (_) {
        if (CORE_API_KEY) headers['X-API-Key'] = CORE_API_KEY;
      }
      const coreWs = new WebSocket(coreWsUrl, { headers });
      coreWs.on('open', () => {
        clientWs.on('message', (data) => {
          if (coreWs.readyState === WebSocket.OPEN) {
            const payload = Buffer.isBuffer(data) ? data.toString('utf8') : (typeof data === 'string' ? data : String(data));
            coreWs.send(payload);
          }
        });
        coreWs.on('message', (data) => {
          if (clientWs.readyState === WebSocket.OPEN) {
            const payload = Buffer.isBuffer(data) ? data.toString('utf8') : (typeof data === 'string' ? data : String(data));
            clientWs.send(payload);
          }
        });
      });
      coreWs.on('error', (err) => {
        console.error('Core WS error:', err.message);
        try { clientWs.close(1011, 'Core connection error'); } catch (_) {}
      });
      coreWs.on('close', () => { try { clientWs.close(); } catch (_) {} });
      clientWs.on('close', () => { try { coreWs.close(); } catch (_) {} });
      clientWs.on('error', () => { try { coreWs.close(); } catch (_) {} });
    });
  }

  return { handleUpgrade };
}

module.exports = { create };
