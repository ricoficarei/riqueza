const path = require('node:path');

module.exports = {
  appId: 'com.maycom.chefcontrol',
  productName: 'MAYCOM CHEF CONTROL',
  executableName: 'MAYCOM CHEF CONTROL',
  copyright: 'MAYCOM CHEF CONTROL',
  asar: true,
  npmRebuild: false,
  electronVersion: '45.2.3',
  toolsets: { nsis: '1.2.1' },
  directories: {
    output: process.env.MAYCOM_WINDOWS_OUTPUT || 'dist',
    buildResources: 'resources',
  },
  files: [
    'main.cjs', 'preload.cjs', 'lib/**', 'resources/icon.png', 'resources/icon.ico',
    'package.json',
  ],
  extraResources: [{
    from: path.resolve(process.env.MAYCOM_BACKEND_DIR || '../desktop/dist/MaycomBackend'),
    to: 'backend',
    filter: ['**/*'],
  }, {
    from: path.resolve(process.env.MAYCOM_LICENSES_DIR || '../desktop/licenses-redistribution'),
    to: 'licenses',
    filter: ['**/*'],
  }, {
    from: path.resolve(__dirname, '../desktop/LEIA-ME-WINDOWS.txt'),
    to: 'LEIA-ME.txt',
  }, {
    from: path.resolve(__dirname, '../docs/LOCAL-GRATUITO.md'),
    to: 'LOCAL-GRATUITO.md',
  }],
  win: {
    target: [{ target: 'portable', arch: ['x64'] }],
    icon: 'resources/icon.ico',
    artifactName: 'MAYCOM-CHEF-CONTROL-Portable-${version}-${arch}.${ext}',
    // The official Electron binary remains unchanged on a Linux cross-build.
    // No signature, TLS, checksum or artifact-integrity verification is disabled.
    signAndEditExecutable: false,
  },
  portable: {
    requestExecutionLevel: 'user',
    // Every launch extracts into a unique directory, so a second click cannot
    // remove files that are in use by the already-running instance.
    unpackDirName: false,
    splashImage: 'resources/splash.bmp',
  },
  publish: null,
};
