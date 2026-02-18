/**
 * Browser actions: navigate, snapshot, click, type, fill, scroll.
 * Each returns { success, text, error }.
 */

const { sessionKey, getPage } = require('./session');

const MAX_SNAPSHOT_ELEMENTS = 100;
const MAX_PAGE_TEXT_CHARS = 50000;

// Single-label hostnames that are valid browser targets; do not treat as node ids.
const BROWSER_HOST_WHITELIST = new Set(['localhost', 'local']);

function looksLikeNodeId(urlOrHost) {
  const s = (urlOrHost || '').trim();
  const host = s.replace(/^https?:\/\//i, '').replace(/\/.*$/, '').split(':')[0];
  if (!host) return false;
  if (BROWSER_HOST_WHITELIST.has(host.toLowerCase())) return false;
  return !host.includes('.') && /^[a-zA-Z0-9][-a-zA-Z0-9]*$/.test(host);
}

async function navigate(params = {}, userId = '') {
  const url = (params.url || '').trim();
  if (!url) return { success: false, text: '', error: 'url is required' };
  if (looksLikeNodeId(url)) {
    return { success: false, text: '', error: `"${url}" looks like a node id, not a URL. For camera/video on a node use node_camera_snap or node_camera_clip with node_id (e.g. capability_id=node_camera_clip, parameters={node_id: "${url}", duration: "3s", includeAudio: true}).` };
  }
  const u = url.startsWith('http://') || url.startsWith('https://') ? url : 'https://' + url;
  if (looksLikeNodeId(u)) {
    const nodeId = (u.replace(/^https?:\/\//i, '').replace(/\/.*$/, '').split(':')[0] || url).trim();
    return { success: false, text: '', error: `"${url}" looks like a node id (${nodeId}), not a URL. For camera/video on a node use node_camera_snap or node_camera_clip with node_id (e.g. capability_id=node_camera_clip, parameters={node_id: "${nodeId}", duration: "3s", includeAudio: true}).` };
  }
  const key = sessionKey(params, userId);
  try {
    const page = await getPage(key);
    await page.goto(u, { waitUntil: 'domcontentloaded', timeout: 30000 });
    const text = await page.evaluate(() => (document.body && document.body.innerText) || '');
    const out = (text || '').trim();
    const maxChars = parseInt(params.max_chars, 10) || MAX_PAGE_TEXT_CHARS;
    const truncated = out.length > maxChars ? out.slice(0, maxChars) + '\n... (truncated)' : out;
    return { success: true, text: truncated || '(no text content)', error: null };
  } catch (e) {
    return { success: false, text: '', error: String(e.message) };
  }
}

async function snapshot(params = {}, userId = '') {
  const key = sessionKey(params, userId);
  try {
    const page = await getPage(key);
    const elements = await page.evaluate((max) => {
      const nodes = document.querySelectorAll('a[href], button, input, textarea, [role="button"], [onclick], [contenteditable="true"]');
      return Array.from(nodes).slice(0, max).map((el, i) => {
        el.setAttribute('data-homeclaw-ref', String(i));
        const text = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim().slice(0, 80);
        return { ref: i, selector: `[data-homeclaw-ref="${i}"]`, text: text || '(no text)', tag: el.tagName.toLowerCase() };
      });
    }, MAX_SNAPSHOT_ELEMENTS);
    const lines = elements.map((e) => `[${e.ref}] ${e.selector} "${e.text}" (${e.tag})`);
    const text = lines.length ? lines.join('\n') : '(no interactive elements found)';
    return { success: true, text, error: null };
  } catch (e) {
    return { success: false, text: '', error: String(e.message) };
  }
}

async function click(params = {}, userId = '') {
  const selector = (params.selector || params.ref == null ? params.selector : `[data-homeclaw-ref="${params.ref}"]`).trim();
  if (!selector) return { success: false, text: '', error: 'selector or ref is required' };
  const key = sessionKey(params, userId);
  try {
    const page = await getPage(key);
    const sel = params.ref != null && params.selector == null ? `[data-homeclaw-ref="${params.ref}"]` : selector;
    await page.click(sel, { timeout: 5000 });
    return { success: true, text: `Clicked: ${sel}`, error: null };
  } catch (e) {
    return { success: false, text: '', error: String(e.message) };
  }
}

async function type(params = {}, userId = '') {
  const selector = (params.selector || '').trim();
  const sel = params.ref != null && !selector ? `[data-homeclaw-ref="${params.ref}"]` : selector;
  const text = params.text != null ? String(params.text) : '';
  if (!sel) return { success: false, text: '', error: 'selector or ref is required' };
  const key = sessionKey(params, userId);
  try {
    const page = await getPage(key);
    await page.fill(sel, text);
    return { success: true, text: `Typed into: ${sel}`, error: null };
  } catch (e) {
    return { success: false, text: '', error: String(e.message) };
  }
}

async function fill(params = {}, userId = '') {
  return type(params, userId);
}

async function scroll(params = {}, userId = '') {
  const direction = (params.direction || 'down').toLowerCase();
  const selector = (params.selector || '').trim();
  const key = sessionKey(params, userId);
  try {
    const page = await getPage(key);
    const delta = direction === 'up' ? -300 : 300;
    if (selector) {
      await page.locator(selector).first().evaluate((el, d) => el.scrollBy(0, d), delta);
    } else {
      await page.evaluate((d) => window.scrollBy(0, d), delta);
    }
    return { success: true, text: `Scrolled ${direction}`, error: null };
  } catch (e) {
    return { success: false, text: '', error: String(e.message) };
  }
}

async function closeSession(params = {}, userId = '') {
  const key = sessionKey(params, userId);
  await require('./session').closeSession(key);
  return { success: true, text: `Closed browser session: ${key}`, error: null };
}

module.exports = {
  navigate,
  snapshot,
  click,
  type,
  fill,
  scroll,
  closeSession,
};
