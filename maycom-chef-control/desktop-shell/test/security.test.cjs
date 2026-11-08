const assert = require('node:assert/strict');
const { test } = require('node:test');
const { validateHandshake, allowedLocalURL, allowedExternalURL } = require('../lib/security.cjs');
const nonce = 'abcdefghijklmnopqrstuvwxyz0123456789';

test('startup accepts only exact loopback origin with one-time bootstrap path', () => {
  const valid = validateHandshake({ url: `http://127.0.0.1:49152/desktop/start/${nonce}`, pid: 123 });
  assert.equal(valid.origin, 'http://127.0.0.1:49152');
  for (const url of [`https://evil.example/desktop/start/${nonce}`, `http://localhost:49152/desktop/start/${nonce}`, `file:///etc/passwd`, `http://user:pass@127.0.0.1:49152/desktop/start/${nonce}`, `http://127.0.0.1:80/desktop/start/${nonce}`, `http://127.0.0.1:49152/desktop/start/short`, `http://127.0.0.1:49152/desktop/start/${nonce}?key=x`]) {
    assert.throws(() => validateHandshake({ url }));
  }
});

test('renderer navigation cannot leave the exact local service', () => {
  const origin = 'http://127.0.0.1:49152';
  assert.equal(allowedLocalURL(origin + '/api/jobs/id/output', origin), true);
  for (const url of ['http://127.0.0.1:49153/', 'http://127.0.0.1.evil.example:49152/', 'https://127.0.0.1:49152/', 'javascript:alert(1)', 'file:///C:/Windows/system.ini']) assert.equal(allowedLocalURL(url, origin), false);
});

test('only explicit HTTPS provider documentation may open outside the app', () => {
  assert.equal(allowedExternalURL('https://fal.ai/models/fal-ai/kling-video'), true);
  assert.equal(allowedExternalURL('https://docs.fal.ai/'), true);
  for (const url of ['https://fal.ai.evil.example/', 'http://fal.ai/', 'https://user:pass@fal.ai/', 'https://fal.ai:8443/', 'file:///C:/test.exe', 'ms-settings:']) assert.equal(allowedExternalURL(url), false);
});
