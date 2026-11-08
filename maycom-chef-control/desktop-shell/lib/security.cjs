const ALLOWED_DOCUMENTATION_HOSTS = new Set(['fal.ai', 'docs.fal.ai']);

function validateHandshake(value) {
  if (!value || typeof value !== 'object' || typeof value.url !== 'string') throw new Error('Invalid backend handshake');
  const url = new URL(value.url);
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || !url.port || url.username || url.password || url.hash || url.search) {
    throw new Error('Unexpected backend origin');
  }
  const port = Number(url.port);
  if (!Number.isInteger(port) || port < 1024 || port > 65535 || !/^\/desktop\/start\/[A-Za-z0-9_-]{24,256}$/.test(url.pathname)) {
    throw new Error('Invalid backend bootstrap');
  }
  return { url: url.href, origin: url.origin };
}

function allowedLocalURL(value, origin) {
  try {
    const url = new URL(value);
    return url.origin === origin && url.protocol === 'http:' && !url.username && !url.password;
  } catch { return false; }
}

function allowedExternalURL(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && ALLOWED_DOCUMENTATION_HOSTS.has(url.hostname) && !url.username && !url.password && (!url.port || url.port === '443');
  } catch { return false; }
}

module.exports = { validateHandshake, allowedLocalURL, allowedExternalURL };
