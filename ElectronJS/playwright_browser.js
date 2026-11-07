// EasySpider's design-browser contract, implemented using Playwright.
const {chromium, devices} = require('playwright-core');
const fs = require('fs');
const path = require('path');
const os = require('os');
const crypto = require('crypto');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const By = {
    xpath: value => 'xpath=' + value, css: value => value, tagName: value => value,
    id: value => '[id=' + JSON.stringify(value) + ']',
};
const Key = {
    HOME: '\uE011', END: '\uE010', SHIFT: '\uE008', CONTROL: '\uE009', COMMAND: '\uE03D',
    ENTER: '\uE007', BACK_SPACE: '\uE003', DELETE: '\uE017', PAGE_DOWN: '\uE00F',
    chord: (...keys) => keys.join('') + '\uE000',
};
const keyNames = {'\uE011':'Home','\uE010':'End','\uE008':'Shift','\uE009':'Control','\uE03D':'Meta',
    '\uE007':'Enter','\uE006':'Enter','\uE003':'Backspace','\uE017':'Delete','\uE00F':'PageDown',
    '\uE00E':'PageUp','\uE004':'Tab','\uE00C':'Escape','\uE012':'ArrowLeft','\uE014':'ArrowRight'};
const modifiers = new Set(['Shift', 'Control', 'Meta', 'Alt']);
function failure(name, message) { const e = new Error(message); e.name = name; return e; }
function unwrap(value) {
    if (value instanceof Element) return value.handle;
    if (Array.isArray(value)) return value.map(unwrap);
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,unwrap(v)]));
    return value;
}
class Element {
    constructor(driver, handle) { this.driver = driver; this.handle = handle; }
    async getText() {
        const label = await this.handle.evaluate(el => el.tagName === 'OPTION' ? el.textContent.replace(/\s+/g, ' ').trim() : null);
        if (label !== null) return label;
        return await this.handle.isVisible() ? this.handle.innerText() : '';
    }
    async getAttribute(name) {
        return this.handle.evaluate((el,n)=>{
            const v=el[n]; if(typeof v==='boolean') return v?'true':null;
            if(typeof v==='string'||typeof v==='number') return String(v);
            return el.getAttribute(n);
        },name);
    }
    async getCssValue(name) { return this.handle.evaluate((el,n)=>getComputedStyle(el).getPropertyValue(n),name); }
    async isEnabled() { return this.handle.isEnabled(); }
    async isSelected() { return this.handle.evaluate(el=>Boolean(el.selected||el.checked)); }
    async click() { return this.driver.action(this.handle.click({timeout:this.driver.timeouts.pageLoad})); }
    async findElements(selector) { return (await this.handle.$$(selector)).map(h=>new Element(this.driver,h)); }
    async sendKeys(...values) {
        if(await this.handle.evaluate(el=>el.tagName==='INPUT'&&el.type==='file'))
            return this.handle.setInputFiles(values.join('').split('\n'));
        await this.handle.focus();
        const pressed = new Set();
        const keyboard = this.driver.page.keyboard;
        try {
            for(const char of values.join('')) {
                const key=keyNames[char];
                if(char==='\uE000') { for(const p of pressed) await keyboard.up(p); pressed.clear(); }
                else if(modifiers.has(key)) { await keyboard.down(key); pressed.add(key); }
                else if(key) await keyboard.press(key);
                else await keyboard.type(char);
            }
        } finally { for(const key of pressed) await keyboard.up(key); }
    }
}
class Select {
    constructor(element) { this.element=element; }
    selectByIndex(index) { return this.element.driver.action(this.element.handle.selectOption({index})); }
    selectByValue(value) { return this.element.driver.action(this.element.handle.selectOption({value})); }
    selectByVisibleText(label) { return this.element.driver.action(this.element.handle.selectOption({label})); }
    async getFirstSelectedOption() {
        for(const option of await this.element.findElements('option')) if(await option.isSelected()) return option;
        throw failure('NoSuchElementError','No selected option');
    }
}
class Browser {
    constructor(context, profile, temporary) {
        this.context=context; this.profile=profile; this.temporary=temporary;
        this.timeouts={implicit:0,pageLoad:30000,script:30000};
        this.pages=new Map(); this.dialog=null; this.waitingDialogs=new Set(); this.pending=new Set();
        this.downloadErrors=[];
        context.on('page', page=>this.register(page));
        context.pages().forEach(page=>this.register(page));
        this.page=context.pages()[0]; this.frame=this.page.mainFrame();
    }
    register(page) {
        if([...this.pages.values()].includes(page)) return;
        this.pages.set(crypto.randomUUID(),page);
        page.on('dialog',dialog=>{this.dialog=dialog; for(const resolve of this.waitingDialogs) resolve();});
        page.on('download', download=>{
            const directory=path.join(this.profile,'Downloads'); fs.mkdirSync(directory,{recursive:true});
            const output=path.join(directory,path.basename(download.suggestedFilename()));
            const promise=download.saveAs(output).catch(e=>this.downloadErrors.push(String(e)));
            this.pending.add(promise); promise.finally(()=>this.pending.delete(promise));
        });
    }
    async action(promise) {
        let resolve;
        const dialogOpened=new Promise(r=>{resolve=r; this.waitingDialogs.add(r);});
        this.pending.add(promise);
        try { return await Promise.race([promise,dialogOpened]); }
        finally {
            this.waitingDialogs.delete(resolve);
            promise.then(()=>this.pending.delete(promise),()=>this.pending.delete(promise));
        }
    }
    async get(url) {
        await this.action(this.page.goto(url,{waitUntil:'domcontentloaded',timeout:this.timeouts.pageLoad}));
        this.frame=this.page.mainFrame();
    }
    async findElements(selector) { return (await this.frame.$$(selector)).map(h=>new Element(this,h)); }
    async findElement(selector) {
        const end=Date.now()+this.timeouts.implicit;
        do { const found=await this.findElements(selector); if(found.length) return found[0]; await delay(10); } while(Date.now()<end);
        throw failure('NoSuchElementError','Element not found: '+selector);
    }
    async findInFrames(selector) {
        for(const frame of this.page.frames().filter(f=>f!==this.page.mainFrame())) {
            const handle=await frame.$(selector);
            if(handle) { this.frame=frame; return new Element(this,handle); }
        }
        throw failure('NoSuchElementError','Element not found in frames: '+selector);
    }
    async executeScript(code,...args) {
        const promise=this.frame.evaluate(({code,args})=>(new Function(code)).apply(window,args),{code,args:unwrap(args)});
        let timer;
        try { return await this.action(Promise.race([promise,new Promise((_,reject)=>{
            timer=setTimeout(()=>reject(failure('TimeoutError','Script timed out')),this.timeouts.script);
        })])); } finally { clearTimeout(timer); }
    }
    async executeAsyncScript(code,...args) {
        const promise=this.frame.evaluate(({code,args})=>new Promise((resolve,reject)=>{
            try {(new Function(code)).apply(window,[...args,resolve]);} catch(error) {reject(error);}
        }),{code,args:unwrap(args)});
        return await this.action(promise);
    }
    async getAllWindowHandles() { return [...this.pages].filter(([,p])=>!p.isClosed()).map(([id])=>id); }
    async getCurrentUrl() { return this.page.url(); }
    async getTitle() { return this.page.title(); }
    switchTo() {
        return {
            defaultContent:async()=>{this.frame=this.page.mainFrame();},
            parentFrame:async()=>{this.frame=this.frame.parentFrame()||this.page.mainFrame();},
            frame:async element=>{this.frame=await element.handle.contentFrame(); if(!this.frame) throw failure('NoSuchFrameError','Frame disappeared');},
            window:async id=>{
                const page=this.pages.get(id); if(!page||page.isClosed()) throw failure('NoSuchWindowError','Window closed');
                this.page=page; this.frame=page.mainFrame();
            },
            alert:()=>({
                accept:()=>this.handleDialog(true), dismiss:()=>this.handleDialog(false),
                getText:async()=>this.dialog?.message(),
            }),
        };
    }
    async handleDialog(accept) {
        if(!this.dialog) throw failure('NoSuchAlertError','No dialog is open');
        const dialog=this.dialog; this.dialog=null;
        if(accept) await dialog.accept(); else await dialog.dismiss();
        await Promise.allSettled([...this.pending]);
    }
    navigate() { return {refresh:async()=>{
        await this.action(this.page.reload({waitUntil:'domcontentloaded',timeout:this.timeouts.pageLoad}));
        this.frame=this.page.mainFrame();
    }}; }
    manage() {
        return {
            setTimeouts:async timeouts=>Object.assign(this.timeouts,timeouts),
            getCookies:async()=>this.context.cookies([this.page.url()]),
            window:()=>({
                getRect:()=>this.page.evaluate(()=>({x:screenX,y:screenY,width:outerWidth,height:outerHeight})),
                setRect:async bounds=>{
                    const session=await this.context.newCDPSession(this.page);
                    try {
                        const {windowId}=await session.send('Browser.getWindowForTarget');
                        await session.send('Browser.setWindowBounds',{windowId,bounds:Object.fromEntries(
                            Object.entries(bounds).map(([k,v])=>[k,Math.round(v)]))});
                    } finally { await session.detach(); }
                },
            }),
        };
    }
    actions() {
        const steps=[], driver=this;
        const chain={
            move({origin}) {steps.push(()=>origin.handle.hover());return chain;},
            click(element) {steps.push(()=>element.click());return chain;},
            doubleClick(element) {steps.push(()=>driver.action(element.handle.dblclick()));return chain;},
            keyDown(key) {steps.push(()=>driver.page.keyboard.down(keyNames[key]||key));return chain;},
            keyUp(key) {steps.push(()=>driver.page.keyboard.up(keyNames[key]||key));return chain;},
            async perform() {try{for(const step of steps) await step();}finally{for(const key of modifiers) await driver.page.keyboard.up(key).catch(()=>{});}},
        }; return chain;
    }
    async wait(condition, timeout=10000) {
        const end=Date.now()+timeout;
        do {const result=await condition(this);if(result)return result;await delay(50);}while(Date.now()<end);
        throw failure('TimeoutError','Condition did not become true');
    }
    async quit() {
        if(this.closed)return; this.closed=true;
        try {await this.context.close();}
        finally {
            const marker=path.join(this.profile,'.easyspider-playwright.json');
            if(fs.existsSync(marker)) {
                try {if(JSON.parse(fs.readFileSync(marker,'utf8')).pid===process.pid)fs.unlinkSync(marker);}catch{}
            }
            if(this.temporary) fs.rmSync(this.profile,{recursive:true,force:true,maxRetries:5,retryDelay:100});
        }
    }
}
async function launchBrowser({executablePath, profile, mobile=false, extensions=[], initScript='', headless=false, userAgent='', locale='zh-CN', timezoneId='Asia/Shanghai'}) {
    const temporary=!profile;
    profile=profile?path.resolve(profile):fs.mkdtempSync(path.join(os.tmpdir(),'easyspider-designer-'));
    let context;
    try {
        context=await chromium.launchPersistentContext(profile,{
            executablePath, headless, noViewport:!mobile, ...(mobile?devices['iPhone XR']:{}),
            ...(userAgent?{userAgent}:{}),
            locale, timezoneId,
            ignoreDefaultArgs:['--enable-automation', '--disable-extensions',
                '--disable-popup-blocking', '--disable-ipc-flooding-protection'],
            args:['--disable-blink-features=AutomationControlled',`--lang=${locale}`,'--enable-unsafe-extension-debugging',
                '--remote-debugging-port=0','--remote-debugging-address=127.0.0.1'],
        });
        if(initScript)await context.addInitScript({content:initScript});
        const session=await context.browser().newBrowserCDPSession();
        const extensionIds=[];
        try { for(const folder of extensions) extensionIds.push((await session.send('Extensions.loadUnpacked',{path:path.resolve(folder)})).id); }
        finally {await session.detach();}
        const lines=fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').trim().split(/\r?\n/);
        const endpoint='ws://127.0.0.1:'+lines[0]+lines[1];
        fs.writeFileSync(path.join(profile,'.easyspider-playwright.json'),JSON.stringify({
            version:1,pid:process.pid,profile,endpoint,app:'EasySpider',
        }),{mode:0o600});
        const driver=new Browser(context,profile,temporary);
        driver.endpoint=endpoint; driver.extensionIds=extensionIds;
        return driver;
    } catch(error) {if(context)await context.close();if(temporary)fs.rmSync(profile,{recursive:true,force:true});throw error;}
}
module.exports={launchBrowser,By,Key,Select,Browser,Element,until:{elementIsEnabled:element=>()=>element.isEnabled()}};
