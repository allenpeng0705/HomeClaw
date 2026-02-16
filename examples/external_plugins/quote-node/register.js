/**
 * Register the Quote (Node.js) plugin with HomeClaw Core.
 * Run: node register.js
 * Requires: Core running (default http://127.0.0.1:9000), no extra deps (uses https for fetch).
 */

const CORE_URL = process.env.CORE_URL || 'http://127.0.0.1:9000';
const PLUGIN_BASE = process.env.PLUGIN_BASE || 'http://127.0.0.1:3111';

const payload = {
  plugin_id: 'quote-node',
  name: 'Quote Plugin (Node.js)',
  description: 'Get a random inspirational quote, or by topic. Use when the user asks for a quote, motivation, or inspiration.',
  description_long: 'Returns random quotes; optional topic (motivation, success, dreams) and style (short/long). Use for: give me a quote, inspire me, quote about success.',
  health_check_url: `${PLUGIN_BASE}/health`,
  type: 'http',
  config: {
    base_url: PLUGIN_BASE,
    path: 'run',
    timeout_sec: 10,
  },
  capabilities: [
    {
      id: 'get_quote',
      name: 'Get random quote',
      description: 'Returns a random inspirational quote. Core will add a brief reflection (post_process).',
      parameters: [
        { name: 'style', type: 'string', required: false, description: 'Output style: short (quote only) or long (with label).' },
      ],
      output_description: '{"text": "quote and author string"}',
      post_process: true,
      post_process_prompt: 'The user received this quote. Add one short sentence (under 15 words) that reflects why this quote matters or how it can inspire them. Do not repeat the quote.',
      method: 'POST',
      path: '/run',
    },
    {
      id: 'get_quote_by_topic',
      name: 'Get quote by topic',
      description: 'Returns a random quote filtered by topic (e.g. motivation, success, dreams).',
      parameters: [
        { name: 'topic', type: 'string', required: true, description: 'Topic: motivation, success, innovation, dreams, perseverance.' },
        { name: 'style', type: 'string', required: false, description: 'Output style: short or long.' },
      ],
      output_description: '{"text": "quote and author string"}',
      post_process: false,
      method: 'POST',
      path: '/run',
    },
  ],
};

async function main() {
  const url = `${CORE_URL.replace(/\/$/, '')}/api/plugins/register`;
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (res.ok && data.registered) {
      console.log('Registered quote-node plugin:', data.plugin_id);
    } else {
      console.error('Registration failed:', res.status, data);
      process.exit(1);
    }
  } catch (e) {
    console.error('Error:', e.message);
    process.exit(1);
  }
}

main();
