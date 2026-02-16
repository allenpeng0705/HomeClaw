#!/usr/bin/env node
/**
 * Minimal TUI stub for HomeClaw Browser plugin (Control UI + browser + canvas + nodes).
 * Run: node tui.js
 * Connects to Core via plugin's WS proxy; future: full TUI with chat + status.
 */
const PORT = process.env.PORT || 3020;
const PLUGIN_WS = process.env.PLUGIN_WS || `ws://127.0.0.1:${PORT}/ws`;

console.log('HomeClaw Browser plugin — TUI');
console.log('  For now, use WebChat in the browser: http://127.0.0.1:' + PORT + '/');
console.log('  TUI (terminal UI) with chat + status will be added in a later step.');
console.log('  Plugin WS proxy:', PLUGIN_WS);
process.exit(0);
