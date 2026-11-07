// Run with Electron (not the host Node) to check the upgraded runtime.
const assert = require('node:assert/strict');
const path = require('node:path');
const {createRequire} = require('node:module');
const appRequire = createRequire(path.resolve(__dirname, '../ElectronJS/package.json'));
const {app} = appRequire('electron');
app.whenReady().then(() => {
    assert.ok(Number(process.versions.node.split('.')[0]) >= 20);
    assert.equal(typeof appRequire('./playwright_browser').launchBrowser, 'function');
    if (process.platform === 'win32') {
        const {windowManager} = appRequire('node-window-manager');
        assert.equal(typeof windowManager.getActiveWindow, 'function');
        assert.ok(windowManager.getActiveWindow());
    }
    console.log('Electron dependency smoke passed: ' + JSON.stringify(process.versions));
    app.quit();
}).catch(error => { console.error(error); app.exit(1); });
