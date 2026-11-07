/*
 * Reproducible Playwright anti-detection audit.
 *
 * The report intentionally records detector summaries and stable local
 * signals, while redacting IP addresses and leaving full detector pages out
 * of source control.  Run from the EasySpider root with `node`.
 */
const fs = require('fs');
const os = require('os');
const path = require('path');
const {launchBrowser} = require('../ElectronJS/playwright_browser');
const ROOT = path.resolve(__dirname, '..');
const CHROME = process.env.EASYSPIDER_CHROME_BINARY ||
    path.join(ROOT, 'ElectronJS', 'chrome_win64', 'chrome.exe');
const DETECTORS = [
    ['Rebrowser', 'https://bot-detector.rebrowser.net/'],
    ['BrowserScan', 'https://www.browserscan.net/bot-detection'],
    ['Brotector', 'https://ttlns.github.io/brotector/?crash=false'],
    ['MickeyJS', 'https://mickeyalton33.github.io/MickeyJS/'],
    ['CreepJS', 'https://abrahamjuliot.github.io/creepjs/'],
    ['BrowserLeaks', 'https://browserleaks.com/javascript'],
    ['Incolumitas', 'https://bot.incolumitas.com/'],
];

function arg(name, fallback) {
    const index = process.argv.indexOf(name);
    return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

function redact(text) {
    return String(text || '')
        .replace(/\b(?:\d{1,3}\.){3}\d{1,3}\b/g, '[redacted-ip]')
        .replace(/([0-9a-f]{1,4}:){2,}[0-9a-f:]+/ig, '[redacted-ip]');
}

function compact(text, limit = 4000) {
    return redact(text).replace(/\s+/g, ' ').slice(0, limit);
}

function enhancedStealth() {
    const file = path.join(ROOT, 'ElectronJS', 'stealth.min.js');
    let source = fs.readFileSync(file, 'utf8');
    const locale = process.env.EASYSPIDER_LOCALE || 'zh-CN';
    const languages = locale.toLowerCase().startsWith('zh') ? ['zh-CN', 'zh'] : [locale, locale.split('-', 1)[0]];
    const cpu = Number.parseInt(process.env.EASYSPIDER_HARDWARE_CONCURRENCY || '', 10) || os.cpus().length || 4;
    source = source.replace('opts:{languages:[]}', `opts:{languages:${JSON.stringify(languages)}}`);
    source = source.replace('opts:{hardwareConcurrency:4}', `opts:{hardwareConcurrency:${Math.min(Math.max(cpu, 1), 256)}}`);
    return source + "\ntry { if (navigator.webdriver !== undefined) Object.defineProperty(Object.getPrototypeOf(navigator), 'webdriver', {get: () => undefined}); } catch (_) {}";
}

async function localProbe(driver) {
    return driver.executeAsyncScript(`
        const done = arguments[arguments.length - 1];
        const worker = new Worker(URL.createObjectURL(new Blob([
            'postMessage({languages:navigator.languages, language:navigator.language,' +
            'hardwareConcurrency:navigator.hardwareConcurrency, webdriver:navigator.webdriver})'
        ])));
        worker.onmessage = event => {
            const descriptor = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(navigator), 'webdriver');
            done({
                language: navigator.language,
                languages: Array.from(navigator.languages || []),
                hardwareConcurrency: navigator.hardwareConcurrency,
                worker: event.data,
                webdriver: navigator.webdriver,
                ownWebdriver: Object.prototype.hasOwnProperty.call(navigator, 'webdriver'),
                webdriverDescriptor: descriptor ? {configurable: descriptor.configurable, enumerable: descriptor.enumerable} : null,
                platform: navigator.platform,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                userAgent: navigator.userAgent,
                cdcGlobals: Object.keys(window).filter(key => /^(cdc_|wdc_|__playwright)/i.test(key)),
            });
            worker.terminate();
        };
    `);
}

async function run() {
    const output = path.resolve(arg('--output', path.join(ROOT, 'Docs', 'playwright-antibot-audit.json')));
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'easyspider-antibot-audit-'));
    const driver = await launchBrowser({
        executablePath: CHROME,
        profile,
        initScript: enhancedStealth(),
        headless: process.env.EASYSPIDER_AUDIT_HEADLESS === '1',
        locale: process.env.EASYSPIDER_LOCALE || 'zh-CN',
        timezoneId: process.env.EASYSPIDER_TIMEZONE || 'Asia/Shanghai',
    });
    const report = {
        generatedAt: new Date().toISOString(),
        configuration: {
            browser: 'bundled Chrome via Playwright persistent context',
            headless: process.env.EASYSPIDER_AUDIT_HEADLESS === '1',
            locale: process.env.EASYSPIDER_LOCALE || 'zh-CN',
            timezone: process.env.EASYSPIDER_TIMEZONE || 'Asia/Shanghai',
            detectorWaitMs: 10000,
        },
        localProbe: null,
        detectors: [],
    };
    try {
        await driver.get('data:text/html,<title>EasySpider Playwright probe</title>');
        report.localProbe = await localProbe(driver);
        for (const [name, url] of DETECTORS) {
            const result = {name, url};
            try {
                await driver.get(url);
                await new Promise(resolve => setTimeout(resolve, 10000));
                result.title = await driver.getTitle();
                result.text = compact(await driver.executeScript('return document.body ? document.body.innerText : ""'));
            } catch (error) {
                result.error = String(error);
            }
            report.detectors.push(result);
        }
    } finally {
        await driver.quit();
        fs.rmSync(profile, {recursive: true, force: true, maxRetries: 3, retryDelay: 100});
    }
    fs.mkdirSync(path.dirname(output), {recursive: true});
    fs.writeFileSync(output, JSON.stringify(report, null, 2), 'utf8');
    console.log(`Wrote ${output}`);
}

run().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
