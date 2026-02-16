/**
 * Browser context settings: color scheme, geolocation, timezone, locale, device (viewport), offline, headers, credentials.
 * All return { success, text, error }. Errors are caught and returned; never throw to caller.
 */

const { sessionKey, getContext, getPage } = require('./session');

// Known devices for viewport emulation (Playwright-style). User agent is set at context creation; we only set viewport here.
const DEVICE_VIEWPORTS = {
  'iPhone 14': { width: 390, height: 844 },
  'iPhone 14 Pro': { width: 393, height: 852 },
  'iPhone SE': { width: 375, height: 667 },
  'Pixel 5': { width: 393, height: 851 },
  'Galaxy S9+': { width: 412, height: 846 },
  'iPad Pro': { width: 1024, height: 1366 },
  'iPad (gen 7)': { width: 810, height: 1080 },
  'Desktop 1280x720': { width: 1280, height: 720 },
  'Desktop 1920x1080': { width: 1920, height: 1080 },
};

async function setColorScheme(params = {}, userId = '') {
  const key = sessionKey(params, userId);
  const raw = (params.color_scheme || params.colorScheme || '').toLowerCase();
  const colorScheme = raw === 'dark' || raw === 'light' || raw === 'no-preference' ? raw : raw === 'none' ? null : undefined;
  if (colorScheme === undefined && raw !== '') {
    return { success: false, text: '', error: 'color_scheme must be dark, light, no-preference, or none' };
  }
  try {
    const context = await getContext(key);
    await context.emulateMedia({ colorScheme: colorScheme || undefined });
    return { success: true, text: `Color scheme set to ${colorScheme ?? 'none'}`, error: null };
  } catch (e) {
    return { success: false, text: '', error: String(e.message) };
  }
}

async function setGeolocation(params = {}, userId = '') {
  const key = sessionKey(params, userId);
  const clear = params.clear === true || params.clear === 'true';
  if (clear) {
    try {
      const context = await getContext(key);
      await context.setGeolocation({ latitude: 0, longitude: 0 });
      return { success: true, text: 'Geolocation cleared', error: null };
    } catch (e) {
      return { success: false, text: '', error: String(e.message) };
    }
  }
  const lat = parseFloat(params.latitude);
  const lon = parseFloat(params.longitude);
  if (Number.isNaN(lat) || Number.isNaN(lon)) {
    return { success: false, text: '', error: 'latitude and longitude are required (numbers)' };
  }
  const accuracy = params.accuracy != null ? parseFloat(params.accuracy) : undefined;
  try {
    const context = await getContext(key);
    await context.grantPermissions(['geolocation']).catch(() => {});
    await context.setGeolocation({ latitude: lat, longitude: lon, accuracy });
    return { success: true, text: `Geolocation set to ${lat}, ${lon}`, error: null };
  } catch (e) {
    return { success: false, text: '', error: String(e.message) };
  }
}

async function setTimezone(params = {}, userId = '') {
  const timezone = (params.timezone || params.timezoneId || '').trim();
  if (!timezone) return { success: false, text: '', error: 'timezone is required (e.g. America/New_York)' };
  const key = sessionKey(params, userId);
  try {
    const context = await getContext(key);
    await context.setTimezoneId(timezone);
    return { success: true, text: `Timezone set to ${timezone}`, error: null };
  } catch (e) {
    return { success: false, text: '', error: String(e.message) };
  }
}

async function setLocale(params = {}, userId = '') {
  const locale = (params.locale || '').trim();
  if (!locale) return { success: false, text: '', error: 'locale is required (e.g. en-US)' };
  const key = sessionKey(params, userId);
  try {
    const context = await getContext(key);
    await context.setExtraHTTPHeaders({ 'Accept-Language': locale });
    return { success: true, text: `Locale (Accept-Language) set to ${locale}`, error: null };
  } catch (e) {
    return { success: false, text: '', error: String(e.message) };
  }
}

async function setDevice(params = {}, userId = '') {
  const device = (params.device || params.deviceName || '').trim();
  if (!device) return { success: false, text: '', error: 'device is required (e.g. iPhone 14, Desktop 1920x1080)' };
  const viewport = DEVICE_VIEWPORTS[device];
  if (!viewport) {
    const names = Object.keys(DEVICE_VIEWPORTS).join(', ');
    return { success: false, text: '', error: `Unknown device. Supported: ${names}` };
  }
  const key = sessionKey(params, userId);
  try {
    const page = await getPage(key);
    await page.setViewportSize(viewport);
    return { success: true, text: `Viewport set to ${device} (${viewport.width}x${viewport.height})`, error: null };
  } catch (e) {
    return { success: false, text: '', error: String(e.message) };
  }
}

async function setOffline(params = {}, userId = '') {
  const key = sessionKey(params, userId);
  const offline = params.offline === true || params.offline === 'true' || String(params.offline).toLowerCase() === 'true';
  try {
    const context = await getContext(key);
    await context.setOffline(offline);
    return { success: true, text: `Offline mode set to ${offline}`, error: null };
  } catch (e) {
    return { success: false, text: '', error: String(e.message) };
  }
}

async function setExtraHeaders(params = {}, userId = '') {
  const key = sessionKey(params, userId);
  const headers = params.headers || params.extra_headers;
  if (!headers || typeof headers !== 'object') {
    return { success: false, text: '', error: 'headers (object) is required' };
  }
  const normalized = {};
  for (const [k, v] of Object.entries(headers)) {
    if (v != null) normalized[k] = String(v);
  }
  try {
    const context = await getContext(key);
    await context.setExtraHTTPHeaders(normalized);
    return { success: true, text: `Extra HTTP headers set (${Object.keys(normalized).length} headers)`, error: null };
  } catch (e) {
    return { success: false, text: '', error: String(e.message) };
  }
}

async function setCredentials(params = {}, userId = '') {
  const key = sessionKey(params, userId);
  const clear = params.clear === true || params.clear === 'true';
  if (clear) {
    try {
      const context = await getContext(key);
      await context.setHTTPCredentials(null);
      return { success: true, text: 'HTTP credentials cleared', error: null };
    } catch (e) {
      return { success: false, text: '', error: String(e.message) };
    }
  }
  const username = (params.username || '').trim();
  const password = params.password != null ? String(params.password) : '';
  if (!username) return { success: false, text: '', error: 'username is required for HTTP credentials' };
  try {
    const context = await getContext(key);
    await context.setHTTPCredentials({ username, password });
    return { success: true, text: 'HTTP credentials set', error: null };
  } catch (e) {
    return { success: false, text: '', error: String(e.message) };
  }
}

module.exports = {
  setColorScheme,
  setGeolocation,
  setTimezone,
  setLocale,
  setDevice,
  setOffline,
  setExtraHeaders,
  setCredentials,
  DEVICE_VIEWPORTS,
};
