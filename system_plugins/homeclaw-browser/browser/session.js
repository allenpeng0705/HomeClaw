/**
 * Per-user (or per-session) browser context. One Playwright browser context per session key.
 * Session key = user_id or capability_parameters.session_id or "default".
 */

const { chromium } = require('playwright');

// YAML may pass boolean false as "False" (Python str); accept "false", "False", "0", "no" as headed.
const HEADLESS = !/^(false|0|no)$/i.test(String(process.env.BROWSER_HEADLESS || '').trim());
const contexts = new Map();
let browser = null;

async function getBrowser() {
  if (!browser) {
    browser = await chromium.launch({
      headless: HEADLESS,
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    });
  }
  return browser;
}

function sessionKey(params = {}, userId = '') {
  const sid = (params.session_id || params.sessionId || '').trim();
  const uid = (userId || '').trim();
  return sid || uid || 'default';
}

async function getContext(sessionKeyStr) {
  if (contexts.has(sessionKeyStr)) {
    const ctx = contexts.get(sessionKeyStr);
    if (ctx && !ctx._closed) return ctx;
    contexts.delete(sessionKeyStr);
  }
  const b = await getBrowser();
  const context = await b.newContext({
    viewport: { width: 1280, height: 720 },
    userAgent: 'Mozilla/5.0 (compatible; HomeClaw-Browser-Plugin/1.0)',
  });
  contexts.set(sessionKeyStr, context);
  context._closed = false;
  context.on('close', () => {
    context._closed = true;
    contexts.delete(sessionKeyStr);
  });
  return context;
}

async function getPage(sessionKeyStr) {
  const context = await getContext(sessionKeyStr);
  const pages = context.pages();
  if (pages.length) return pages[0];
  return context.newPage();
}

async function closeSession(sessionKeyStr) {
  const ctx = contexts.get(sessionKeyStr);
  if (ctx && !ctx._closed) {
    await ctx.close();
    contexts.delete(sessionKeyStr);
  }
  return true;
}

function listSessions() {
  return Array.from(contexts.keys());
}

module.exports = {
  sessionKey,
  getContext,
  getPage,
  closeSession,
  listSessions,
  getBrowser,
};
