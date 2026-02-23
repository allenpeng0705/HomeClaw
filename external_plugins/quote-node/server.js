/**
 * External Quote Plugin - Node.js HTTP server.
 * Run: npm start  (or node server.js)
 * Then register with Core: npm run register  (or curl; see README)
 *
 * Contract: GET /health (2xx), POST /run body=PluginRequest JSON, response=PluginResult JSON.
 */

const http = require('http');

const PORT = process.env.PORT || 3111;

const QUOTES = [
  ['The only way to do great work is to love what you do.', 'Steve Jobs', 'motivation'],
  ['Innovation distinguishes between a leader and a follower.', 'Steve Jobs', 'innovation'],
  ['Stay hungry, stay foolish.', 'Steve Jobs', 'motivation'],
  ['The future belongs to those who believe in the beauty of their dreams.', 'Eleanor Roosevelt', 'dreams'],
  ['Success is not final, failure is not fatal.', 'Winston Churchill', 'success'],
  ['The only impossible journey is the one you never begin.', 'Tony Robbins', 'motivation'],
];

function getRandomQuote(topic = null, style = null) {
  let pool = QUOTES;
  if (topic) {
    const topicLower = topic.toLowerCase();
    const filtered = QUOTES.filter((q) => (q[2] || '').toLowerCase().includes(topicLower));
    if (filtered.length) pool = filtered;
  }
  const [quote, author] = pool[Math.floor(Math.random() * pool.length)];
  if (style && style.toLowerCase() === 'short') {
    return `"${quote}" — ${author}`;
  }
  return `Quote: "${quote}"\nAuthor: ${author}`;
}

const server = http.createServer((req, res) => {
  const url = req.url || '/';
  const method = req.method;

  if (method === 'GET' && (url === '/health' || url === '/')) {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok' }));
    return;
  }

  if (method === 'POST' && url === '/run') {
    let body = '';
    req.on('data', (chunk) => { body += chunk; });
    req.on('end', () => {
      try {
        const data = JSON.parse(body);
        const requestId = data.request_id || '';
        const pluginId = data.plugin_id || 'quote';
        const capId = (data.capability_id || 'get_quote').toString().trim().toLowerCase().replace(/\s+/g, '_');
        const params = data.capability_parameters || {};
        const topic = (params.topic || '').trim() || null;
        const style = (params.style || '').trim() || null;

        let text;
        if (capId === 'get_quote_by_topic') {
          text = getRandomQuote(topic, style);
        } else {
          text = getRandomQuote(null, style);
        }

        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          request_id: requestId,
          plugin_id: pluginId,
          success: true,
          text,
          error: null,
          metadata: {},
        }));
      } catch (e) {
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          request_id: '',
          plugin_id: 'quote',
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

server.listen(PORT, '0.0.0.0', () => {
  console.log(`Quote plugin (Node.js) listening on http://0.0.0.0:${PORT}`);
});
