const { app, BrowserWindow, dialog, session, shell } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const { validateHandshake, allowedLocalURL, allowedExternalURL } = require('./lib/security.cjs');

const APP_NAME = 'MAYCOM CHEF CONTROL';
const START_TIMEOUT_MS = 150000;
const CONTENT_POLICY = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self' data:; connect-src 'self'; object-src 'none'; frame-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'";
let mainWindow;
let backend;
let quitting = false;
let stopping = false;
let backendOrigin = null;
let exitCode = 0;

app.setName(APP_NAME);
app.setAppUserModelId('com.maycom.chefcontrol');
const smokeIndex = process.argv.indexOf('--smoke-test');
const smokeReport = smokeIndex >= 0 ? process.argv[smokeIndex + 1] : null;
if (smokeIndex >= 0 && !smokeReport) process.exit(2);

function errorPage(message) {
  const safe = message.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
  return `<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>${APP_NAME}</title><style>body{margin:0;background:#0b0c10;color:#e9e5f0;font:16px system-ui;display:grid;place-items:center;height:100vh}.panel{max-width:480px;padding:40px}h1{font-size:19px;letter-spacing:2px;color:#b49ada}p{line-height:1.7;color:#b5afc3}.line{height:2px;width:110px;background:#a58ace;margin:25px 0}</style><main class="panel"><h1>${APP_NAME}</h1><div class="line"></div><p>${safe}</p></main></html>`;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    title: APP_NAME, width: 1480, height: 1000, minWidth: 900, minHeight: 680,
    show: false, backgroundColor: '#0b0c10', autoHideMenuBar: true,
    icon: path.join(__dirname, 'resources', 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true, nodeIntegration: false, sandbox: true,
      webSecurity: true, allowRunningInsecureContent: false, devTools: !app.isPackaged,
    },
  });
  mainWindow.setMenu(null);
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (allowedExternalURL(url)) void shell.openExternal(url);
    return { action: 'deny' };
  });
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (!backendOrigin || !allowedLocalURL(url, backendOrigin)) {
      event.preventDefault();
      if (allowedExternalURL(url)) void shell.openExternal(url);
    }
  });
  mainWindow.once('ready-to-show', () => mainWindow?.show());
  mainWindow.on('closed', () => { mainWindow = null; });
  void mainWindow.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(errorPage('Preparando seu estúdio. Na primeira abertura, a preparação pode levar alguns instantes…')));
}

function setupSession(origin) {
  const current = session.defaultSession;
  current.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  current.setPermissionCheckHandler(() => false);
  current.setDevicePermissionHandler(() => false);
  current.webRequest.onBeforeRequest((details, callback) => {
    const internal = allowedLocalURL(details.url, origin) || details.url.startsWith('blob:') || details.url.startsWith('data:');
    callback({ cancel: !internal });
  });
  current.webRequest.onHeadersReceived((details, callback) => {
    callback({ responseHeaders: { ...details.responseHeaders, 'Content-Security-Policy': [CONTENT_POLICY] } });
  });
  current.on('will-download', (_event, item) => {
    if (!allowedLocalURL(item.getURL(), origin)) { item.cancel(); return; }
    item.setSaveDialogOptions({ title: 'Salvar vídeo — MAYCOM CHEF CONTROL', defaultPath: path.join(app.getPath('downloads'), path.basename(item.getFilename())) });
  });
}

function startBackend() {
  const backendDir = app.isPackaged ? path.join(process.resourcesPath, 'backend') : path.resolve(process.env.MAYCOM_BACKEND_DIR || path.join(__dirname, '../desktop/dist/MaycomBackend'));
  const executable = path.join(backendDir, 'MaycomBackend.exe');
  if (!fs.existsSync(executable)) return Promise.reject(new Error('O componente do estúdio não foi encontrado. Baixe novamente o aplicativo portátil completo.'));
  return new Promise((resolve, reject) => {
    let buffer = '';
    let settled = false;
    const timeout = setTimeout(() => finish(new Error('O estúdio demorou além do esperado para iniciar. Feche o aplicativo e tente novamente.')), START_TIMEOUT_MS);
    function finish(error, handshake) {
      if (settled) return;
      settled = true; clearTimeout(timeout);
      if (error) reject(error); else resolve(handshake);
    }
    backend = spawn(executable, ['--server'], { cwd: backendDir, stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true, shell: false });
    backend.once('error', () => finish(new Error('Não foi possível iniciar o estúdio. Confira se o arquivo portátil foi extraído corretamente.')));
    backend.once('exit', () => {
      if (!settled) finish(new Error('O estúdio não conseguiu iniciar. Seus arquivos pessoais permanecem na pasta do aplicativo.'));
      else if (!quitting && mainWindow) {
        dialog.showErrorBox(APP_NAME, 'O processamento local foi encerrado. Feche e abra novamente o aplicativo.');
        app.quit();
      }
    });
    backend.stdout.on('data', chunk => {
      if (settled) return;
      buffer += chunk.toString('utf8');
      if (buffer.length > 16384) { finish(new Error('Resposta de inicialização inválida. Baixe novamente o aplicativo.')); return; }
      const newline = buffer.indexOf('\n');
      if (newline < 0) return;
      try { finish(null, validateHandshake(JSON.parse(buffer.slice(0, newline)))); }
      catch { finish(new Error('Não foi possível estabelecer uma conexão segura com o estúdio local.')); }
    });
    // Backend diagnostics may contain private filenames. Do not copy their
    // raw content into dialogs, renderer messages or telemetry.
    backend.stderr.on('data', () => {});
    backend.stdin.on('error', () => {});
  });
}

async function stopBackend() {
  if (!backend || backend.exitCode !== null || stopping) return;
  stopping = true;
  const child = backend;
  await new Promise(resolve => {
    let finished = false;
    const finish = () => { if (!finished) { finished = true; clearTimeout(timer); resolve(); } };
    const timer = setTimeout(() => {
      if (process.platform === 'win32' && Number.isInteger(child.pid)) {
        // Kill only the child tree created by this application, never a global
        // Python process or a PID supplied by the renderer/backend handshake.
        const killer = spawn('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore', shell: false });
        killer.once('exit', finish); killer.once('error', finish);
        setTimeout(finish, 2000);
      } else { child.kill('SIGTERM'); finish(); }
    }, 5000);
    child.once('exit', finish);
    child.stdin.end();
  });
}

async function smokeCheck() {
  let result;
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    result = await mainWindow.webContents.executeJavaScript(`(async()=>({title:document.title,health:await (await fetch('/api/health')).json(),sources:document.querySelectorAll('input[type=file]').length}))()`);
    if (result.sources === 2 && result.health.status === 'ok') break;
    await new Promise(resolve => setTimeout(resolve, 300));
  }
  if (!result.title.includes(APP_NAME) || result.health.app_name !== APP_NAME || result.sources !== 2) throw new Error('O teste da janela não encontrou a interface esperada.');
  const report = { passed: true, app_name: APP_NAME, title: result.title, health: result.health.status, source_inputs: result.sources, electron: process.versions.electron, chrome: process.versions.chrome };
  fs.mkdirSync(path.dirname(path.resolve(smokeReport)), { recursive: true });
  const image = await mainWindow.webContents.capturePage();
  fs.writeFileSync(smokeReport + '.png', image.toPNG(), { flag: 'wx' });
  fs.writeFileSync(smokeReport, JSON.stringify(report, null, 2), { flag: 'wx' });
}

const primary = app.requestSingleInstanceLock();
if (!primary) app.quit();
else {
  app.on('second-instance', () => { if (mainWindow) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.show(); mainWindow.focus(); } });
  app.on('before-quit', event => {
    if (quitting) return;
    event.preventDefault(); quitting = true;
    void stopBackend().finally(() => app.exit(exitCode));
  });
  app.on('window-all-closed', () => app.quit());
  app.whenReady().then(async () => {
    createWindow();
    try {
      const handshake = await startBackend();
      if (quitting || !mainWindow) return;
      backendOrigin = handshake.origin;
      setupSession(backendOrigin);
      await mainWindow.loadURL(handshake.url);
      if (smokeReport) { await smokeCheck(); app.quit(); }
    } catch (error) {
      if (quitting) return;
      if (smokeReport) {
        exitCode = 1;
        try {
          fs.mkdirSync(path.dirname(path.resolve(smokeReport)), { recursive: true });
          fs.writeFileSync(smokeReport, JSON.stringify({ passed: false, error: error.message }), { flag: 'wx' });
        } catch { /* Preserve existing reports and still exit with failure. */ }
        app.quit();
      } else {
        await mainWindow?.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(errorPage(error.message)));
        dialog.showErrorBox(APP_NAME, error.message);
      }
    }
  });
}
