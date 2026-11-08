const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

const root = path.resolve(__dirname, '..');
const backendDir = path.resolve(process.env.MAYCOM_BACKEND_DIR || path.join(root, '../desktop/dist/MaycomBackend'));
const licensesDir = path.resolve(process.env.MAYCOM_LICENSES_DIR || path.join(root, '../desktop/licenses-redistribution'));
for (const notice of ['PYTHON-LICENSE.txt', 'FFMPEG-LICENSE.txt', 'THIRD-PARTY-NOTICES.md']) {
  if (!fs.existsSync(path.join(licensesDir, notice))) throw new Error(`Provide the redistribution licenses before packaging: ${path.join(licensesDir, notice)}`);
}
const executable = path.join(backendDir, 'MaycomBackend.exe');
if (!fs.existsSync(executable)) throw new Error(`Build the real bundled backend first: ${executable}`);
const fd = fs.openSync(executable, 'r');
const signature = Buffer.alloc(2); fs.readSync(fd, signature, 0, 2, 0); fs.closeSync(fd);
if (signature.toString('ascii') !== 'MZ' || fs.statSync(executable).size < 1024 * 1024) throw new Error('The backend must be a real bundled Windows executable.');
execFileSync(process.execPath, [require.resolve('electron-builder/out/cli/cli.js'), '--config', path.join(root, 'electron-builder.config.cjs'), '--win', 'portable', '--x64', '--publish', 'never'], {
  cwd: root, stdio: 'inherit', env: {
    ...process.env, MAYCOM_BACKEND_DIR: backendDir, MAYCOM_LICENSES_DIR: licensesDir,
    ELECTRON_CACHE: process.env.ELECTRON_CACHE || path.resolve(root, '../.data/build-cache/electron'),
    ELECTRON_BUILDER_CACHE: process.env.ELECTRON_BUILDER_CACHE || path.resolve(root, '../.data/build-cache/electron-builder'),
    ELECTRON_GET_USE_PROXY: process.env.ELECTRON_GET_USE_PROXY || '1',
  },
});
