/**
 * HomeClaw Browser Plugin - HTTP server.
 * Contract: GET /health (2xx), POST /run body=PluginRequest JSON, response=PluginResult JSON.
 * GET / -> WebChat (Control UI); WS /ws -> proxy to Core /ws.
 * GET /canvas -> canvas viewer; WS /canvas-ws?session=... for live updates.
 * GET /nodes -> nodes page; WS /nodes-ws for node registration.
 * Run: npm start  (or node server.js)
 * Then register with Core: npm run register
 * Env: CORE_URL (default http://127.0.0.1:9000), CORE_API_KEY (optional), PORT (default 3020).
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const { WebSocketServer } = require('ws');
const { handleRun } = require('./run-handler');
const canvasStore = require('./canvas/store');
const canvasPush = require('./canvas/push');
const nodeRegistry = require('./nodes/registry');
const nodeCommand = require('./nodes/command');
const PORT = process.env.PORT || 3020;
const CORE_URL = (process.env.CORE_URL || 'http://127.0.0.1:9000').replace(/\/$/, '');
const CORE_WS_URL = CORE_URL.replace(/^http/, 'ws') + '/ws';
const CORE_API_KEY = process.env.CORE_API_KEY || '';
const PUBLIC_DIR = path.join(__dirname, 'public');
const CONTROL_UI_DIR = path.join(__dirname, 'control-ui');
const controlUiWs = require('./control-ui/ws-proxy').create({ CORE_WS_URL, CORE_API_KEY });

function serveStatic(filePath, res, defaultFile) {
  const reqPath = (filePath === '/' || filePath === '') && defaultFile ? defaultFile : filePath;
  const fullPath = path.join(PUBLIC_DIR, (reqPath || 'index.html').split('?')[0]);
  if (!fullPath.startsWith(PUBLIC_DIR)) {
    res.writeHead(403);
    res.end();
    return;
  }
  fs.readFile(fullPath, (err, data) => {
    if (err) {
      res.writeHead(404);
      res.end('Not Found');
      return;
    }
    const ext = path.extname(fullPath);
    const types = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.ico': 'image/x-icon' };
    res.writeHead(200, { 'Content-Type': types[ext] || 'application/octet-stream' });
    res.end(data);
  });
}

const server = http.createServer((req, res) => {
  const url = req.url || '/';
  const method = req.method;

  if (method === 'GET' && url === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok' }));
    return;
  }

  if (method === 'GET' && (url === '/' || url === '/index.html' || url.startsWith('/webchat'))) {
    const controlUiIndex = path.join(CONTROL_UI_DIR, 'index.html');
    fs.readFile(controlUiIndex, (err, data) => {
      if (err) {
        res.writeHead(404);
        res.end('Not Found');
        return;
      }
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(data);
    });
    return;
  }

  if (method === 'GET' && (url === '/canvas' || url === '/canvas/')) {
    serveStatic('/canvas.html', res, 'canvas.html');
    return;
  }

  if (method === 'GET' && (url === '/nodes' || url === '/nodes/')) {
    serveStatic('/nodes.html', res, 'nodes.html');
    return;
  }

  if (method === 'GET' && url === '/api/nodes') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(nodeRegistry.list()));
    return;
  }

  if (method === 'GET' && url.startsWith('/') && (url.endsWith('.html') || url.endsWith('.js') || url.endsWith('.css'))) {
    serveStatic(url, res, null);
    return;
  }

  if (method === 'POST' && (url === '/api/upload' || url.startsWith('/api/upload'))) {
    const coreUploadUrl = CORE_URL + '/api/upload';
    const parsed = new URL(coreUploadUrl);
    const headers = { ...req.headers, host: parsed.host };
    if (CORE_API_KEY) headers['x-api-key'] = CORE_API_KEY;
    const httpModule = parsed.protocol === 'https:' ? require('https') : require('http');
    const proxyReq = httpModule.request(
      coreUploadUrl,
      { method: 'POST', headers },
      (proxyRes) => {
        res.writeHead(proxyRes.statusCode, proxyRes.headers);
        proxyRes.pipe(res);
      }
    );
    proxyReq.on('error', (e) => {
      res.writeHead(502, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: String(e.message), paths: [] }));
    });
    req.pipe(proxyReq);
    return;
  }

  if (method === 'POST' && url === '/run') {
    // Allow long-running node commands (e.g. camera_snap/clip can wait up to CMD_TIMEOUT_MS). Prevent Node/socket timeout from closing the request.
    const RUN_TIMEOUT_MS = 360000; // 6 min, must be > nodes/command.js CMD_TIMEOUT_MS
    if (req.socket) req.socket.setTimeout(RUN_TIMEOUT_MS);
    let body = '';
    req.on('data', (chunk) => { body += chunk; });
    req.on('end', async () => {
      try {
        const data = JSON.parse(body);
        const result = await handleRun(data);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(result));
      } catch (e) {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          request_id: '',
          plugin_id: 'homeclaw-browser',
          success: false,
          text: '',
          error: String(e.message),
          metadata: {},
        }));
      }
    });
    return;
  }

  res.writeHead(404);
  res.end('Not Found');
});

const canvasWss = new WebSocketServer({ noServer: true });
const nodesWss = new WebSocketServer({ noServer: true });

server.on('upgrade', (request, socket, head) => {
  const url = new URL(request.url || '', `http://${request.headers.host || 'localhost'}`);
  if (url.pathname === '/ws') {
    controlUiWs.handleUpgrade(request, socket, head);
    return;
  }
  if (url.pathname === '/canvas-ws') {
    const session = (url.searchParams.get('session') || '').trim() || 'default';
    canvasWss.handleUpgrade(request, socket, head, (ws) => {
      canvasPush.subscribe(session, ws);
      const doc = canvasStore.get(session);
      if (doc) {
        try {
          ws.send(JSON.stringify({ type: 'canvas_update', document: doc }));
        } catch (e) {}
      }
    });
    return;
  }
  if (url.pathname === '/nodes-ws') {
    nodesWss.handleUpgrade(request, socket, head, (ws) => {
      let registered = false;
      ws.on('message', (data) => {
        if (registered) {
          nodeCommand.handleNodeMessage(null, data);
          return;
        }
        try {
          const msg = JSON.parse(data.toString());
          if (msg.type === 'register' && (msg.node_id || msg.nodeId)) {
            const nodeId = String(msg.node_id || msg.nodeId);
            const capabilities = msg.capabilities || ['canvas', 'screen', 'camera', 'location'];
            nodeRegistry.register(nodeId, ws, capabilities);
            registered = true;
            ws.on('message', (data) => nodeCommand.handleNodeMessage(nodeId, data));
            ws.send(JSON.stringify({ type: 'registered', node_id: nodeId }));
          }
        } catch (e) {}
      });
    });
    return;
  }
  socket.destroy();
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`HomeClaw Browser plugin listening on http://0.0.0.0:${PORT}`);
  console.log(`  WebChat:  http://127.0.0.1:${PORT}/`);
  console.log(`  Canvas:   http://127.0.0.1:${PORT}/canvas`);
  console.log(`  Nodes:    http://127.0.0.1:${PORT}/nodes`);
  console.log(`  WS proxy: ws://127.0.0.1:${PORT}/ws -> ${CORE_WS_URL}`);
});
