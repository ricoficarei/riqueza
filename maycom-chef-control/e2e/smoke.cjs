/* Browser checks against the real backend. Synthetic fixtures are uploads only;
 * this test never fabricates a generated result or calls paid inference. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { execFileSync } = require('node:child_process');
const { chromium } = require('playwright');

async function main() {
  const baseURL = process.env.MAYCOM_TEST_URL || 'http://127.0.0.1:8000';
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'maycom-browser-fixtures-'));
  const artifacts = path.resolve(__dirname, 'artifacts');
  fs.mkdirSync(artifacts, { recursive: true });
  const image = path.join(temp, 'test-only-character.png');
  const video = path.join(temp, 'test-only-reference.mp4');
  const python = process.env.MAYCOM_TEST_PYTHON || path.resolve(__dirname, '../backend/.venv/bin/python');
  execFileSync(python, ['-c', "from PIL import Image,ImageDraw; import sys; i=Image.new('RGB',(400,600),'#211c38'); d=ImageDraw.Draw(i); d.ellipse((150,60,250,160),fill='#9a82cc'); d.rectangle((120,170,280,480),fill='#75609e'); i.save(sys.argv[1])", image]);
  execFileSync('ffmpeg', ['-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=24:duration=4', '-c:v', 'libx264', '-threads', '2', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', video]);
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width: 1536, height: 1080 }, reducedMotion: 'reduce' });
  const page = await context.newPage();
  const errors = [];
  const uploaded = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto(baseURL, { waitUntil: 'networkidle' });
    assert.match(await page.title(), /MAYCOM CHEF CONTROL/);
    await page.getByRole('heading', { name: 'Sua identidade. Em movimento.' }).waitFor();
    const capabilities = await (await context.request.get(`${baseURL}/api/capabilities`)).json();
    assert.equal(capabilities.provider.configured, false, 'Run this browser test without a configured local model.');
    assert.equal(await page.getByRole('button', { name: 'GENERATE VIDEO', exact: true }).isDisabled(), true);
    assert.equal(await page.locator('.empty-preview').count(), 1);
    await page.screenshot({ path: path.join(artifacts, 'studio-desktop.png'), fullPage: true });

    for (const [index, file, name] of [[0, image, 'test-only-character.png'], [1, video, 'test-only-reference.mp4']]) {
      const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/assets') && response.request().method() === 'POST');
      await page.locator('input[type=file]').nth(index).setInputFiles(file);
      const response = await responsePromise;
      assert.equal(response.status(), 201, await response.text());
      uploaded.push((await response.json()).id);
      await page.locator('.asset-name').filter({ hasText: name }).waitFor();
    }
    assert.equal(await page.locator('.uploaded-media img').evaluate(el => el.complete && el.naturalWidth > 0), true);
    await page.waitForFunction(() => document.querySelector('.uploaded-media video')?.readyState >= 1);
    assert.equal(await page.locator('.asset-review-row').count(), 2);
    assert.equal(await page.getByRole('button', { name: 'GENERATE VIDEO', exact: true }).isDisabled(), true);

    await page.getByRole('button', { name: 'Revisar arquivo', exact: true }).first().click();
    const review = page.getByRole('dialog', { name: 'Autorização antes da criação.' });
    await review.waitFor();
    assert.equal(await review.getByRole('button', { name: 'Aprovar arquivo' }).isDisabled(), true);
    await page.getByRole('button', { name: 'Fechar revisão' }).click();

    await page.getByRole('button', { name: 'Nova criação' }).click();
    assert.equal(await page.locator('.empty-preview').count(), 1);
    assert.equal(await page.locator('.uploaded-media').count(), 0, 'New creation must reset selected sources, while keeping stored files in the library.');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(artifacts, 'studio-mobile.png'), fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), true, 'Mobile page overflows horizontally.');
    assert.deepEqual(errors, [], 'The browser raised JavaScript errors.');
    console.log('PASS: real UI, API connection, image/video uploads, playable source media, review gate, generation unavailable without a local model, desktop/mobile layout, no JS errors.');
  } finally {
    try {
      for (const id of uploaded) {
        const response = await context.request.delete(`${baseURL}/api/assets/${id}`);
        assert.equal(response.status(), 204, 'Browser fixture cleanup failed.');
      }
    } finally {
      await browser.close();
      fs.rmSync(temp, { recursive: true, force: true });
    }
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
