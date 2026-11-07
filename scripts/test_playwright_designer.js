// Browser contract used by Electron's recorder and node debugger.
const assert = require('node:assert/strict');
const http = require('node:http');
const path = require('node:path');
const {launchBrowser, By, Key, Select} = require('../ElectronJS/playwright_browser');

async function main() {
    const server = http.createServer((req, res) => {
        res.writeHead(200, {'Content-Type': 'text/html; charset=utf-8'});
        if (req.url === '/frame') return res.end('<!doctype html><button id="inside">Frame</button>');
        if (req.url.startsWith('/result')) return res.end('<!doctype html><title>Submitted</title><h1>Done</h1>');
        if (req.url === '/popup') return res.end('<!doctype html><title>Popup</title>Popup');
        res.end(`<!doctype html><title>Designer contract</title>
            <form action="/result"><input name="q" id="q"><button id="submit">Submit</button></form>
            <select id="choice" onchange="document.body.dataset.answer=confirm('choice?')?'yes':'no'">
            <option value="a">One</option><option value="b">Two</option></select>
            <button id="popup" onclick="window.open('/popup')">Popup</button>
            <button id="hover" onmouseover="this.dataset.hover='yes'" ondblclick="this.dataset.double='yes'">Hover</button>
            <iframe id="frame" src="/frame"></iframe>`);
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    let driver;
    try {
        driver = await launchBrowser({
            executablePath: path.resolve(__dirname, '../ElectronJS/chrome_win64/chrome.exe'), headless: true,
        });
        await driver.get('http://127.0.0.1:' + server.address().port);
        const field = await driver.findElement(By.xpath('//input[@name="q"]'));
        await field.sendKeys('old', Key.chord(Key.CONTROL, 'a'), 'new');
        assert.equal(await field.getAttribute('value'), 'new');
        const choice = new Select(await driver.findElement(By.id('choice')));
        await choice.selectByValue('b');
        assert.equal(await driver.switchTo().alert().getText(), 'choice?');
        await driver.switchTo().alert().dismiss();
        assert.equal(await (await choice.getFirstSelectedOption()).getText(), 'Two');
        assert.equal(await driver.executeScript('return document.body.dataset.answer'), 'no');
        await choice.selectByIndex(0);
        await driver.switchTo().alert().accept();
        assert.equal(await driver.executeScript('return document.body.dataset.answer'), 'yes');
        const hovered = await driver.findElement(By.id('hover'));
        await driver.actions().move({origin: hovered}).doubleClick(hovered).perform();
        assert.equal(await hovered.getAttribute('data-double'), 'yes');
        assert.equal(await hovered.getAttribute('data-hover'), 'yes');
        await driver.switchTo().frame(await driver.findElement(By.id('frame')));
        await driver.wait(async () => (await driver.findElements(By.id('inside'))).length);
        assert.equal(await (await driver.findElement(By.id('inside'))).getText(), 'Frame');
        await driver.switchTo().defaultContent();
        const original = (await driver.getAllWindowHandles())[0];
        await (await driver.findElement(By.id('popup'))).click();
        await driver.wait(async () => (await driver.getAllWindowHandles()).length === 2);
        const popup = (await driver.getAllWindowHandles()).find(id => id !== original);
        await driver.switchTo().window(popup);
        await driver.wait(async () => (await driver.getTitle()) === 'Popup');
        await driver.page.close();
        await driver.switchTo().window(original);
        await driver.executeScript("document.cookie='fixture=ok; SameSite=Lax; path=/'");
        assert.ok((await driver.manage().getCookies()).some(c => c.name === 'fixture' && c.value === 'ok'));
        await (await driver.findElement(By.id('submit'))).click();
        await driver.wait(async () => (await driver.getTitle()) === 'Submitted');
        assert.match(await driver.getCurrentUrl(), /q=new/);
        console.log('Designer contract passed: input/chords/select/dialog/hover/double-click/iframe/popup/cookies/navigation');
    } finally {
        if (driver) await driver.quit();
        await new Promise(resolve => server.close(resolve));
    }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
