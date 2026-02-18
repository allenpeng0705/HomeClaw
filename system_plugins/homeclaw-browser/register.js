/**
 * Register the HomeClaw Browser plugin with Core.
 * Run: node register.js
 * Requires: Core running (default http://127.0.0.1:9000).
 * This plugin provides: browser automation, canvas, nodes, and Control UI (WebChat, dashboard).
 * When using for browser actions, set tools.browser_enabled: false in config/core.yml.
 */

const CORE_URL = process.env.CORE_URL || 'http://127.0.0.1:9000';
const PLUGIN_BASE = process.env.PLUGIN_BASE || 'http://127.0.0.1:3020';

const payload = {
  plugin_id: 'homeclaw-browser',
  name: 'HomeClaw Browser',
  description: 'Browser automation (navigate, snapshot, click, type), canvas (push title/blocks to /canvas), nodes (list/send commands), and Control UI (WebChat at /, WS proxy to Core). Use when the user asks to: open a URL or interact with a web page; update or show content on the canvas; list nodes or send a command to a node; or open WebChat/dashboard to chat with the agent.',
  description_long: 'Playwright-based browser automation in Node.js. One browser context per user/session. Capabilities: browser_navigate, browser_snapshot, browser_click, browser_type, browser_fill, browser_scroll, browser_close_session; canvas_update (push UI to canvas viewer); node_list, node_command. Set tools.browser_enabled: false in Core to use this plugin for browser actions.',
  health_check_url: `${PLUGIN_BASE}/health`,
  type: 'http',
  config: {
    base_url: PLUGIN_BASE,
    path: 'run',
    timeout_sec: 420,  // 7 min: must exceed plugin→node timeout (5 min) so Core doesn't ReadTimeout before plugin responds
  },
  capabilities: [
    {
      id: 'browser_navigate',
      name: 'Navigate to URL',
      description: 'Open a URL in the browser and return the page text. Call browser_snapshot next to get clickable elements, then browser_click or browser_type.',
      parameters: [
        { name: 'url', type: 'string', required: true, description: 'URL to open (e.g. https://example.com).' },
        { name: 'max_chars', type: 'integer', required: false, description: 'Max characters to return (default 50000).' },
        { name: 'session_id', type: 'string', required: false, description: 'Optional session key; omit to use user_id.' },
      ],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
    {
      id: 'browser_snapshot',
      name: 'Get page snapshot',
      description: 'Get interactive elements (buttons, links, inputs) on the current page with refs and selectors. Use these with browser_click or browser_type. Requires an open page (call browser_navigate first).',
      parameters: [
        { name: 'session_id', type: 'string', required: false, description: 'Optional session key.' },
      ],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
    {
      id: 'browser_click',
      name: 'Click element',
      description: 'Click an element on the current page. Use selector from browser_snapshot (e.g. [data-homeclaw-ref="0"]) or ref (0, 1, 2...).',
      parameters: [
        { name: 'selector', type: 'string', required: false, description: 'CSS selector of the element to click.' },
        { name: 'ref', type: 'integer', required: false, description: 'Ref index from browser_snapshot (0, 1, 2...).' },
        { name: 'session_id', type: 'string', required: false, description: 'Optional session key.' },
      ],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
    {
      id: 'browser_type',
      name: 'Type into input',
      description: 'Type text into an input or textarea. Clears the field first. Use selector or ref from browser_snapshot.',
      parameters: [
        { name: 'selector', type: 'string', required: false, description: 'CSS selector of the input/textarea.' },
        { name: 'ref', type: 'integer', required: false, description: 'Ref index from browser_snapshot.' },
        { name: 'text', type: 'string', required: true, description: 'Text to type.' },
        { name: 'session_id', type: 'string', required: false, description: 'Optional session key.' },
      ],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
    {
      id: 'browser_fill',
      name: 'Fill input',
      description: 'Clear and fill an input (same as browser_type). Use selector or ref from browser_snapshot.',
      parameters: [
        { name: 'selector', type: 'string', required: false, description: 'CSS selector of the input.' },
        { name: 'ref', type: 'integer', required: false, description: 'Ref index from browser_snapshot.' },
        { name: 'text', type: 'string', required: true, description: 'Text to fill.' },
        { name: 'session_id', type: 'string', required: false, description: 'Optional session key.' },
      ],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
    {
      id: 'browser_scroll',
      name: 'Scroll page',
      description: 'Scroll the page or an element. Use after browser_navigate to see more content.',
      parameters: [
        { name: 'direction', type: 'string', required: false, description: 'up or down (default down).' },
        { name: 'selector', type: 'string', required: false, description: 'Optional element selector to scroll.' },
        { name: 'session_id', type: 'string', required: false, description: 'Optional session key.' },
      ],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
    {
      id: 'browser_close_session',
      name: 'Close browser session',
      description: 'Close the browser context for this user/session to free resources.',
      parameters: [
        { name: 'session_id', type: 'string', required: false, description: 'Session to close; omit to use user_id.' },
      ],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
    {
      id: 'browser_set_color_scheme',
      name: 'Set color scheme',
      description: 'Set the page color scheme (prefers-color-scheme): dark, light, no-preference, or none.',
      parameters: [
        { name: 'color_scheme', type: 'string', required: true, description: 'dark, light, no-preference, or none.' },
        { name: 'session_id', type: 'string', required: false, description: 'Optional session key.' },
      ],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
    {
      id: 'browser_set_geolocation',
      name: 'Set geolocation',
      description: 'Set or clear geolocation for the page (for location-aware sites).',
      parameters: [
        { name: 'latitude', type: 'number', required: false, description: 'Latitude (required unless clear).' },
        { name: 'longitude', type: 'number', required: false, description: 'Longitude (required unless clear).' },
        { name: 'accuracy', type: 'number', required: false, description: 'Optional accuracy in meters.' },
        { name: 'clear', type: 'boolean', required: false, description: 'Set true to clear geolocation.' },
        { name: 'session_id', type: 'string', required: false, description: 'Optional session key.' },
      ],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
    {
      id: 'browser_set_timezone',
      name: 'Set timezone',
      description: 'Set browser timezone (e.g. America/New_York).',
      parameters: [
        { name: 'timezone', type: 'string', required: true, description: 'IANA timezone (e.g. America/New_York).' },
        { name: 'session_id', type: 'string', required: false, description: 'Optional session key.' },
      ],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
    {
      id: 'browser_set_locale',
      name: 'Set locale',
      description: 'Set Accept-Language header (e.g. en-US).',
      parameters: [
        { name: 'locale', type: 'string', required: true, description: 'Locale (e.g. en-US).' },
        { name: 'session_id', type: 'string', required: false, description: 'Optional session key.' },
      ],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
    {
      id: 'browser_set_device',
      name: 'Set device viewport',
      description: 'Set viewport size for device emulation (e.g. iPhone 14, Desktop 1920x1080).',
      parameters: [
        { name: 'device', type: 'string', required: true, description: 'Device name: iPhone 14, iPad Pro, Pixel 5, Desktop 1920x1080, etc.' },
        { name: 'session_id', type: 'string', required: false, description: 'Optional session key.' },
      ],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
    {
      id: 'browser_set_offline',
      name: 'Set offline mode',
      description: 'Emulate offline (true) or online (false).',
      parameters: [
        { name: 'offline', type: 'boolean', required: true, description: 'true = offline, false = online.' },
        { name: 'session_id', type: 'string', required: false, description: 'Optional session key.' },
      ],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
    {
      id: 'browser_set_extra_headers',
      name: 'Set extra HTTP headers',
      description: 'Set extra headers for requests from this context.',
      parameters: [
        { name: 'headers', type: 'object', required: true, description: 'Object of header name -> value.' },
        { name: 'session_id', type: 'string', required: false, description: 'Optional session key.' },
      ],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
    {
      id: 'browser_set_credentials',
      name: 'Set HTTP credentials',
      description: 'Set or clear HTTP Basic auth credentials for this context.',
      parameters: [
        { name: 'username', type: 'string', required: false, description: 'Username (required unless clear).' },
        { name: 'password', type: 'string', required: false, description: 'Password.' },
        { name: 'clear', type: 'boolean', required: false, description: 'Set true to clear credentials.' },
        { name: 'session_id', type: 'string', required: false, description: 'Optional session key.' },
      ],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
    {
      id: 'canvas_update',
      name: 'Update canvas',
      description: 'Push content to the canvas viewer (the page at /canvas). Use when the user asks to "update the canvas", "show on the canvas", or "put a title and button on the canvas". Call with document: { title: string, blocks: [ { type: "text", content } | { type: "button", label } ] }. The canvas page at http://plugin:3020/canvas shows this in real time.',
      parameters: [
        { name: 'document', type: 'object', required: false, description: 'Canvas document: { title?: string, blocks: [{ type: "text", content: string } | { type: "button", label: string, id?: string }] }.' },
        { name: 'title', type: 'string', required: false, description: 'Short title (if not using document.title).' },
        { name: 'blocks', type: 'array', required: false, description: 'Array of blocks (if not using document.blocks).' },
        { name: 'session_id', type: 'string', required: false, description: 'Session key for the canvas viewer; omit to use user_id.' },
      ],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
    {
      id: 'node_list',
      name: 'List nodes',
      description: 'List connected nodes (devices that registered with the plugin). Returns node_id and capabilities (e.g. canvas, screen, camera, location).',
      parameters: [],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
    {
      id: 'node_command',
      name: 'Send command to node',
      description: 'Send a command to a connected node (e.g. screen, camera, canvas). The node must be connected via /nodes-ws and registered. Node responds with result.',
      parameters: [
        { name: 'node_id', type: 'string', required: true, description: 'Node id from node_list.' },
        { name: 'command', type: 'string', required: true, description: 'Command: notify, camera_snap, camera_clip, screen_record, location_get, or custom.' },
        { name: 'params', type: 'object', required: false, description: 'Optional parameters for the command.' },
      ],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
    {
      id: 'node_notify',
      name: 'Node notify',
      description: 'Send a system notification on the node (e.g. system.notify). Convenience for node_command with command "notify".',
      parameters: [
        { name: 'node_id', type: 'string', required: true, description: 'Node id from node_list.' },
        { name: 'title', type: 'string', required: false, description: 'Notification title.' },
        { name: 'body', type: 'string', required: false, description: 'Notification body.' },
      ],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
    {
      id: 'node_camera_snap',
      name: 'Node camera snap',
      description: 'Take a photo on the node (front/back/both). Returns MEDIA path. Node must support camera_snap.',
      parameters: [
        { name: 'node_id', type: 'string', required: true, description: 'Node id from node_list.' },
        { name: 'facing', type: 'string', required: false, description: 'front, back, or both.' },
        { name: 'maxWidth', type: 'number', required: false, description: 'Max width in pixels.' },
      ],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
    {
      id: 'node_camera_clip',
      name: 'Node camera clip',
      description: 'Record a short video clip from the node camera. Node must support camera_clip.',
      parameters: [
        { name: 'node_id', type: 'string', required: true, description: 'Node id from node_list.' },
        { name: 'facing', type: 'string', required: false, description: 'front or back.' },
        { name: 'duration', type: 'string', required: false, description: 'Duration (e.g. 5s).' },
        { name: 'includeAudio', type: 'boolean', required: false, description: 'Include microphone.' },
      ],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
    {
      id: 'node_screen_record',
      name: 'Node screen record',
      description: 'Start or get screen recording from the node. Node must support screen_record.',
      parameters: [
        { name: 'node_id', type: 'string', required: true, description: 'Node id from node_list.' },
        { name: 'fps', type: 'number', required: false, description: 'Frames per second.' },
        { name: 'duration', type: 'string', required: false, description: 'Duration (e.g. 10s).' },
      ],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
    {
      id: 'node_location_get',
      name: 'Node location get',
      description: 'Get device location from the node (lat/lon/accuracy). Node must support location_get.',
      parameters: [
        { name: 'node_id', type: 'string', required: true, description: 'Node id from node_list.' },
        { name: 'maxAgeMs', type: 'number', required: false, description: 'Max age of cached location (ms).' },
      ],
      post_process: false,
      method: 'POST',
      path: '/run',
    },
  ],
  ui: {
    webchat: PLUGIN_BASE + '/',
    control: PLUGIN_BASE + '/',
    dashboard: PLUGIN_BASE + '/',
    tui: 'node ' + __dirname + '/tui.js',
    custom: [
      { id: 'webchat', name: 'WebChat', url: PLUGIN_BASE + '/' },
      { id: 'canvas', name: 'Canvas', url: `${PLUGIN_BASE}/canvas` },
      { id: 'nodes', name: 'Nodes', url: `${PLUGIN_BASE}/nodes` },
    ],
  },
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
      console.log('Registered homeclaw-browser plugin:', data.plugin_id);
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
