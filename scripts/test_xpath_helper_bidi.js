#!/usr/bin/env node
// Historical test filename retained; the designer now loads extensions via Playwright/CDP.
const http = require('http');
const path = require('path');
const assert = require('node:assert/strict');
const electronRoot = process.env.EASYSPIDER_ELECTRON_ROOT
  ? path.resolve(process.env.EASYSPIDER_ELECTRON_ROOT) : path.resolve(__dirname, '../ElectronJS');
const {launchBrowser, By} = require(path.join(electronRoot, 'playwright_browser'));
const chromeBinary = path.join(electronRoot, 'chrome_win64', 'chrome.exe');

async function main() {
  const server = http.createServer((req, res) => {
    res.writeHead(200, {'Content-Type':'text/html; charset=utf-8'});
    res.end('<!doctype html><title>Extension test</title><h1 id="smoke-title">XPath Smoke Test</h1>');
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    for (const language of ['zh', 'en']) {
      const driver = await launchBrowser({executablePath:chromeBinary,
        extensions:[path.join(electronRoot, 'EasySpider_' + language), path.join(electronRoot, 'XPathHelper_MV3')],
        headless:process.env.HEADED !== '1'});
      try {
        assert.equal(driver.extensionIds.length, 2);
        await driver.get('http://127.0.0.1:' + server.address().port + '/');
        // The document_idle content script installs its keyboard listener after
        // DOMContentLoaded; the iframe is inserted only after the first hotkey.
        await driver.wait(async () => {
          if (await driver.page.locator('#xh-bar').count()) return true;
          await driver.page.keyboard.press('Control+Shift+X');
          await new Promise(resolve => setTimeout(resolve, 300));
          return await driver.page.locator('#xh-bar').count();
        });
        await driver.page.waitForSelector('#xh-bar:not(.hidden)');
        await driver.switchTo().frame(await driver.findElement(By.id('xh-bar')));
        const query = await driver.findElement(By.id('query'));
        await query.handle.fill('');
        await query.sendKeys('//h1');
        try {
          await driver.wait(async () => (await (await driver.findElement(By.id('node-count'))).getText()) === '1');
        } catch (error) {
          console.error(await driver.executeScript("return {query:document.getElementById('query').value,count:document.getElementById('node-count').textContent,result:document.getElementById('results').value}"));
          throw error;
        }
        const result = await (await driver.findElement(By.id('results'))).getAttribute('value');
        assert.match(result, /XPath Smoke Test/);
        await driver.switchTo().defaultContent();
        assert.equal(await driver.executeScript("return document.querySelectorAll('.xh-highlight').length"), 1);
        // Extension content script must actually be present; an install ID alone is insufficient.
        assert.ok(await driver.page.locator('#xh-bar').count());
        console.log(JSON.stringify({language, extensionIds:driver.extensionIds, xpathMatches:1, result}));
      } finally { await driver.quit(); }
    }
  } finally { await new Promise(resolve => server.close(resolve)); }
}
main().catch(error => {console.error(error); process.exitCode=1;});
