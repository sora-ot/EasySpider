// Package an isolated Windows x64 app and exercise its installed browser backend.
// No release cleanup script, user profile, task or upstream Git operation is used.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {createRequire} = require('node:module');
const {spawnSync} = require('node:child_process');
const root = path.resolve(__dirname, '..');
const appDir = path.join(root, 'ElectronJS');
const fromForge = createRequire(path.join(appDir, 'node_modules/@electron-forge/cli/package.json'));
const fromCore = createRequire(fromForge.resolve('@electron-forge/core'));
const packager = fromCore('electron-packager');

function findArchive(directory, name) {
    if (!fs.existsSync(directory)) return null;
    for (const item of fs.readdirSync(directory, {withFileTypes: true})) {
        const candidate = path.join(directory, item.name);
        if (item.isFile() && item.name === name) return candidate;
        if (item.isDirectory()) {
            const found = findArchive(candidate, name);
            if (found) return found;
        }
    }
    return null;
}

async function main() {
    assert.equal(process.platform, 'win32', 'This packaging smoke targets Windows x64');
    const version = JSON.parse(fs.readFileSync(path.join(appDir, 'node_modules/electron/package.json'))).version;
    const archiveName = `electron-v${version}-win32-x64.zip`;
    const archive = findArchive(path.join(process.env.LOCALAPPDATA, 'electron/Cache'), archiveName);
    assert.ok(archive, 'Install Electron first so its verified download is cached');
    const buildRoot = path.join(root, 'ExecuteStage/build_playwright');
    fs.mkdirSync(buildRoot, {recursive: true});
    const output = fs.mkdtempSync(path.join(buildRoot, 'electron-package-'));
    const allowed = new Set(['package.json', 'main.js', 'server.js', 'playwright_browser.js',
        'mime.json', 'stealth.min.js', 'favicon.ico', 'favicon.icns', 'node_modules',
        'src', 'EasySpider_en', 'EasySpider_zh', 'XPathHelper_MV3', 'chrome_win64']);
    const packages = await packager({
        dir: appDir, out: output, name: 'EasySpider', executableName: 'EasySpider',
        electronVersion: version, electronZipDir: path.dirname(archive),
        arch: 'x64', platform: 'win32', asar: false, overwrite: false,
        icon: path.join(appDir, 'favicon.ico'),
        ignore: file => {
            const relative = file.replaceAll('\\', '/').replace(/^\/+/, '');
            if (!relative) return false;
            return !allowed.has(relative.split('/')[0]) || /(^|\/)(chromedriver[^/]*|debug\.log)$/.test(relative);
        },
    });
    assert.equal(packages.length, 1);
    const installed = path.join(packages[0], 'resources/app');
    assert.ok(fs.existsSync(path.join(installed, 'playwright_browser.js')));
    for (const excluded of ['user_data', 'TempUserDataFolder', 'tasks', 'execution_instances', 'Data'])
        assert.ok(!fs.existsSync(path.join(installed, excluded)), excluded);
    const code = `
        const assert = require('node:assert/strict');
        const path = require('node:path');
        const root = process.cwd();
        const {launchBrowser, By} = require('./playwright_browser');
        assert.equal(typeof require('node-window-manager').windowManager.getActiveWindow, 'function');
        (async () => {
            const browser = await launchBrowser({
                executablePath: path.join(root, 'chrome_win64/chrome.exe'), headless: true,
                extensions: [path.join(root, 'EasySpider_zh'), path.join(root, 'XPathHelper_MV3')],
            });
            try {
                await browser.get('data:text/html,<title>Packaged Playwright</title><input id=q>');
                const field = await browser.findElement(By.id('q'));
                await field.sendKeys('packaged');
                assert.equal(await field.getAttribute('value'), 'packaged');
                assert.equal(await browser.getTitle(), 'Packaged Playwright');
                assert.equal(browser.extensionIds.length, 2);
                console.log('Packaged Electron backend passed');
            } finally { await browser.quit(); }
        })().catch(error => { console.error(error); process.exitCode = 1; });
    `;
    const child = spawnSync(path.join(packages[0], 'EasySpider.exe'), ['-e', code], {
        cwd: installed, env: {...process.env, ELECTRON_RUN_AS_NODE: '1'},
        encoding: 'utf8', timeout: 90000, windowsHide: true,
    });
    process.stdout.write(child.stdout || '');
    process.stderr.write(child.stderr || '');
    if (child.error) throw child.error;
    assert.equal(child.status, 0);
    assert.match(child.stdout, /Packaged Electron backend passed/);
    console.log(JSON.stringify({electron: version, packagedPath: packages[0], passed: true}));
}
main().catch(error => { console.error(error); process.exitCode = 1; });
