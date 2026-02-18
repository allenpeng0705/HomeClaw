/**
 * Handle POST /run: parse PluginRequest, dispatch by capability_id, return PluginResult.
 */

const actions = require('./browser/actions');
const settings = require('./browser/settings');
const canvasStore = require('./canvas/store');
const canvasPush = require('./canvas/push');
const nodeRegistry = require('./nodes/registry');
const nodeCommand = require('./nodes/command');

const CAP_MAP = {
  browser_navigate: actions.navigate,
  browser_snapshot: actions.snapshot,
  browser_click: actions.click,
  browser_type: actions.type,
  browser_fill: actions.fill,
  browser_scroll: actions.scroll,
  browser_close_session: actions.closeSession,
  browser_set_color_scheme: settings.setColorScheme,
  browser_set_geolocation: settings.setGeolocation,
  browser_set_timezone: settings.setTimezone,
  browser_set_locale: settings.setLocale,
  browser_set_device: settings.setDevice,
  browser_set_offline: settings.setOffline,
  browser_set_extra_headers: settings.setExtraHeaders,
  browser_set_credentials: settings.setCredentials,
  canvas_update: null, // handled below
};

function normalizeCapId(id) {
  return (id || '').toString().trim().toLowerCase().replace(/\s+/g, '_');
}

// Extract first URL from text (e.g. "open https://www.baidu.com" -> "https://www.baidu.com")
function extractUrlFromText(text) {
  if (!text || typeof text !== 'string') return null;
  const withProtocol = text.match(/https?:\/\/[^\s"'<>)\]]+/i);
  if (withProtocol) return withProtocol[0].replace(/[.,;:!?)]+$/, '');
  const hostOnly = text.match(/(?:^|\s)([a-zA-Z0-9][-a-zA-Z0-9.]*\.[a-zA-Z]{2,})(?:\s|$|[,;:!?)])/);
  return hostOnly ? 'https://' + hostOnly[1] : null;
}

async function handleRun(body) {
  const requestId = body.request_id || '';
  const pluginId = body.plugin_id || 'homeclaw-browser';
  let capId = normalizeCapId(body.capability_id);
  const rawParams = body.capability_parameters;
  let params = (rawParams && typeof rawParams === 'object' && !Array.isArray(rawParams)) ? rawParams : {};
  const userId = (body.user_id || '').trim();
  const userInput = (body.user_input || '').trim();

  // When no capability_id: if user_input contains a URL, treat as browser_navigate (e.g. "open https://www.baidu.com")
  if (!capId && userInput) {
    const url = extractUrlFromText(userInput) || (params.url && String(params.url).trim());
    if (url) {
      capId = 'browser_navigate';
      params = { ...params, url };
    }
  }

  // When still no capability_id: infer from user_input for node actions (e.g. "take a photo on test-node-1" -> node_camera_snap)
  if (!capId && userInput) {
    const nodeIdFromParams = (params.node_id || params.nodeId || '').trim();
    const nodeIdFromText = userInput.match(/(?:on\s+)([a-zA-Z0-9_-]+)/i)?.[1] || userInput.match(/([a-zA-Z0-9]+-node-[a-zA-Z0-9]+)/i)?.[1];
    const nodeId = nodeIdFromParams || nodeIdFromText || '';
    const lower = userInput.toLowerCase();
    if (nodeId && (lower.includes('photo') || lower.includes('take a photo') || lower.includes('snap'))) {
      capId = 'node_camera_snap';
      params = { ...params, node_id: nodeId };
    } else if (nodeId && (lower.includes('record') && lower.includes('video') || lower.includes('video') && lower.includes('record'))) {
      capId = 'node_camera_clip';
      params = { ...params, node_id: nodeId };
    } else if (lower.includes('node') && (lower.includes('list') || lower.includes('connected') || lower.includes('what nodes'))) {
      capId = 'node_list';
    }
  }

  if (capId === 'canvas_update') {
    try {
      const key = canvasStore.sessionKey(params, userId);
      const document = params.document != null ? params.document : { title: params.title || '', blocks: params.blocks || [] };
      canvasStore.set(key, document);
      canvasPush.push(key, canvasStore.get(key));
      return {
        request_id: requestId,
        plugin_id: pluginId,
        success: true,
        text: `Canvas updated for session: ${key}`,
        error: null,
        metadata: {},
      };
    } catch (e) {
      return {
        request_id: requestId,
        plugin_id: pluginId,
        success: false,
        text: '',
        error: String(e.message),
        metadata: {},
      };
    }
  }

  if (capId === 'node_list') {
    try {
      const list = nodeRegistry.list();
      const text = list.length ? list.map(n => `${n.node_id}: ${(n.capabilities || []).join(', ')}`).join('\n') : 'No nodes connected.';
      return {
        request_id: requestId,
        plugin_id: pluginId,
        success: true,
        text,
        error: null,
        metadata: {},
      };
    } catch (e) {
      return { request_id: requestId, plugin_id: pluginId, success: false, text: '', error: String(e.message), metadata: {} };
    }
  }

  if (capId === 'node_command') {
    const nodeId = (params.node_id || params.nodeId || '').trim();
    const command = (params.command || '').trim();
    if (!nodeId || !command) {
      return {
        request_id: requestId,
        plugin_id: pluginId,
        success: false,
        text: '',
        error: 'node_id and command are required',
        metadata: {},
      };
    }
    try {
      const result = await nodeCommand.sendCommand(nodeId, command, params.params || params);
      const metadata = result.media != null ? { media: result.media } : {};
      return {
        request_id: requestId,
        plugin_id: pluginId,
        success: result.success,
        text: result.text || '',
        error: result.error || null,
        metadata,
      };
    } catch (e) {
      return { request_id: requestId, plugin_id: pluginId, success: false, text: '', error: String(e.message), metadata: {} };
    }
  }

  // Node convenience capabilities: map to node_command so agent has first-class actions
  const NODE_CONVENIENCE = {
    node_notify: 'notify',
    node_camera_snap: 'camera_snap',
    node_camera_clip: 'camera_clip',
    node_screen_record: 'screen_record',
    node_location_get: 'location_get',
  };
  const nodeCmd = NODE_CONVENIENCE[capId];
  if (nodeCmd) {
    const nodeId = (params.node_id || params.nodeId || '').trim();
    if (!nodeId) {
      return {
        request_id: requestId,
        plugin_id: pluginId,
        success: false,
        text: '',
        error: 'node_id is required',
        metadata: {},
      };
    }
    const cmdParams = { ...params };
    delete cmdParams.node_id;
    delete cmdParams.nodeId;
    try {
      const result = await nodeCommand.sendCommand(nodeId, nodeCmd, cmdParams);
      const metadata = result.media != null ? { media: result.media } : {};
      return {
        request_id: requestId,
        plugin_id: pluginId,
        success: result.success,
        text: result.text || '',
        error: result.error || null,
        metadata,
      };
    } catch (e) {
      return { request_id: requestId, plugin_id: pluginId, success: false, text: '', error: String(e.message), metadata: {} };
    }
  }

  const fn = CAP_MAP[capId];
  if (!fn) {
    const allCaps = [...Object.keys(CAP_MAP).filter(k => CAP_MAP[k] !== null), ...Object.keys(NODE_CONVENIENCE)];
    const hint = !capId ? ' Pass capability_id (e.g. browser_navigate) and parameters (e.g. url), or include a URL in your message.' : '';
    return {
      request_id: requestId,
      plugin_id: pluginId,
      success: false,
      text: '',
      error: `Unknown or missing capability: "${capId || '(empty)'}". Supported: ${allCaps.join(', ')}.${hint}`,
      metadata: {},
    };
  }

  try {
    const result = await fn(params, userId);
    return {
      request_id: requestId,
      plugin_id: pluginId,
      success: result.success,
      text: result.text || '',
      error: result.error || null,
      metadata: {},
    };
  } catch (e) {
    return {
      request_id: requestId,
      plugin_id: pluginId,
      success: false,
      text: '',
      error: String(e.message),
      metadata: {},
    };
  }
}

module.exports = { handleRun };
