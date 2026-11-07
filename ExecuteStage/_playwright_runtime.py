"""Playwright objects live on one asynchronous browser thread, never callers."""
import asyncio
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.parse import urlsplit
import uuid

from playwright.async_api import async_playwright, Error, TimeoutError


class Runtime:
    def __init__(self, facade):
        self.facade = facade
        self.elements = {}
        self.pages = {}
        self.page = self.frame = self.context = self.browser = None
        self.dialog = None
        self.dialog_event = asyncio.Event()
        self.pending = set()
        self.lock = asyncio.Lock()
        self.page_timeout = 30
        self.script_timeout = 30
        self.implicit_timeout = 0
        self.attached = False
        self.temporary = None
        self.download_errors = []
        self.logs = []

    async def start(self, options, endpoint=None):
        self.pw = await async_playwright().start()
        if endpoint:
            self.attached = True
            self.browser = await self.pw.chromium.connect_over_cdp(endpoint, timeout=10000)
            self.context = self.browser.contexts[0]
        else:
            profile, args = None, []
            for arg in options.arguments:
                if arg.startswith("--user-data-dir="):
                    profile = arg.split("=", 1)[1].strip('"')
                elif arg.startswith("--headless") or arg == "--remote-debugging-pipe":
                    continue
                else:
                    args.append(arg)
            if not profile:
                self.temporary = tempfile.TemporaryDirectory(prefix="easyspider-pw-")
                profile = self.temporary.name
            profile = str(Path(profile).resolve())
            prefs = options.experimental_options.get("prefs", {})
            self.downloads = Path(prefs.get("download.default_directory") or Path(profile) / "Downloads").resolve()
            self.downloads.mkdir(parents=True, exist_ok=True)
            # Persist Chromium preferences, including PDF downloads, before launch.
            pref_file = Path(profile) / "Default" / "Preferences"
            pref_file.parent.mkdir(parents=True, exist_ok=True)
            existing = json.loads(pref_file.read_text("utf-8")) if pref_file.exists() else {}
            for key, value in prefs.items():
                target = existing
                parts = key.split(".")
                for part in parts[:-1]:
                    target = target.setdefault(part, {})
                target[parts[-1]] = value
            pref_file.write_text(json.dumps(existing), encoding="utf-8")
            config = dict(headless=any(a.startswith("--headless") for a in options.arguments),
                          args=args, accept_downloads=True, no_viewport=True,
                          ignore_default_args=["--enable-automation"] if "enable-automation" in
                          options.experimental_options.get("excludeSwitches", []) else [])
            if options.binary_location:
                config["executable_path"] = str(Path(options.binary_location).resolve())
            else:
                config["channel"] = "chrome"
            mobile = options.experimental_options.get("mobileEmulation")
            if mobile:
                device = dict(self.pw.devices[mobile["deviceName"]])
                device.pop("default_browser_type", None)
                config.update(device)
                config["no_viewport"] = False
            self.context = await self.pw.chromium.launch_persistent_context(profile, **config)
            self.browser = self.context.browser
        self.context.on("page", self.register_page)
        for page in self.context.pages:
            self.register_page(page)
        self.page = self.context.pages[-1] if self.context.pages else await self.context.new_page()
        self.frame = self.page.main_frame

    def register_page(self, page):
        if page in self.pages.values():
            return
        self.pages[uuid.uuid4().hex] = page
        page.on("dialog", self.on_dialog)
        page.on("console", lambda message: self.logs.append({
            "level": {"error": "SEVERE", "warning": "WARNING"}.get(message.type, "INFO"),
            "message": message.text,
            "source": "console-api",
            "timestamp": int(time.time() * 1000),
        }))
        if not self.attached:
            page.on("download", lambda download: self.background(self.save_download(download)))

    def background(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.pending.add(task)
        task.add_done_callback(self.pending.discard)
        return task

    async def save_download(self, download):
        staging = None
        try:
            target = self.downloads / Path(download.suggested_filename).name
            stem, suffix = target.stem, target.suffix
            i = 2
            while target.exists():
                target = target.with_name(f"{stem}_{i}{suffix}")
                i += 1
            staging = target.with_name(target.name + '.' + uuid.uuid4().hex + '.crdownload')
            await download.save_as(str(staging))
            os.replace(staging, target)
        except Exception as exc:
            self.download_errors.append(str(exc))
        finally:
            if staging and staging.exists():
                staging.unlink(missing_ok=True)

    def on_dialog(self, dialog):
        self.dialog = dialog
        self.dialog_event.set()

    async def action(self, coroutine, timeout=None):
        """Return control on a dialog so callers can use switch_to.alert."""
        task = asyncio.create_task(coroutine)
        waiter = asyncio.create_task(self.dialog_event.wait())
        try:
            done, _ = await asyncio.wait([task, waiter], timeout=timeout or self.page_timeout + 1,
                                        return_when=asyncio.FIRST_COMPLETED)
            if task in done:
                return task.result()
            if waiter in done and self.dialog:
                self.pending.add(task)
                task.add_done_callback(self.pending.discard)
                return None
            task.cancel()
            from playwright_driver import TimeoutException
            raise TimeoutException("Browser operation timed out")
        finally:
            waiter.cancel()

    async def dispatch(self, name, *args):
        from playwright_driver import (TimeoutException, JavascriptException, InvalidSelectorException,
            StaleElementReferenceException, ElementClickInterceptedException, WebDriverException)
        async with self.lock:
            try:
                return await getattr(self, name)(*args)
            except TimeoutError as exc:
                if "intercepts pointer events" in str(exc):
                    raise ElementClickInterceptedException(str(exc)) from exc
                raise TimeoutException(str(exc)) from exc
            except Error as exc:
                message = str(exc)
                if "not attached" in message or "has been disposed" in message or (name == 'element' and 'Execution context was destroyed' in message):
                    raise StaleElementReferenceException(message) from exc
                if "not a valid" in message or "Unexpected token" in message:
                    raise InvalidSelectorException(message) from exc
                if name == "script":
                    raise JavascriptException(message) from exc
                raise WebDriverException(message) from exc

    def wrap_element(self, handle):
        from playwright_driver import WebElement
        key = uuid.uuid4().hex
        self.elements[key] = handle
        return WebElement(self.facade, key)

    def unwrap(self, value):
        from playwright_driver import WebElement
        if isinstance(value, WebElement):
            if value._driver is not self.facade:
                raise ValueError("Element belongs to a different browser")
            return self.elements[value._key]
        if isinstance(value, (list, tuple)):
            return [self.unwrap(x) for x in value]
        if isinstance(value, dict):
            return {k: self.unwrap(v) for k, v in value.items()}
        return value

    async def wrap_result(self, handle):
        if handle.as_element():
            return self.wrap_element(handle.as_element())
        # Primitive/undefined results need no further page evaluation. A script
        # may already have navigated away by the time its result is inspected.
        value = await handle.json_value()
        if not isinstance(value, (dict, list)):
            await handle.dispose()
            return value
        # Most scripts return JSON (including large AI observations). Serialize
        # them in one call; inspect properties only when DOM nodes are present.
        contains_nodes = await handle.evaluate("""v => {
            const seen = new Set();
            function visit(x) {
                if (!x || typeof x !== 'object' || seen.has(x)) return false;
                if (x instanceof Node) return true;
                seen.add(x); return Object.values(x).some(visit);
            } return visit(v);
        }""")
        if not contains_nodes:
            try:
                return value
            finally:
                await handle.dispose()
        props = await handle.get_properties()
        result = {k: await self.wrap_result(v) for k, v in props.items()}
        array = await handle.evaluate("v => Array.isArray(v) || v instanceof NodeList || v instanceof HTMLCollection")
        await handle.dispose()
        return [result[str(i)] for i in range(len(result))] if array else result

    async def find(self, by, value, many, iframe=False):
        from playwright_driver import _selector, NoSuchElementException
        deadline = asyncio.get_running_loop().time() + self.implicit_timeout
        navigation_deadline = asyncio.get_running_loop().time() + self.page_timeout
        while True:
            frames = [f for f in self.page.frames if f != self.page.main_frame] if iframe else [self.frame]
            for frame in frames:
                if frame.is_detached():
                    continue
                selector = _selector(by, value)
                if not selector.startswith(('xpath=', 'text=')):
                    selector = 'css:light=' + selector
                try:
                    handles = await frame.query_selector_all(selector)
                except Error as exc:
                    if 'Execution context was destroyed' not in str(exc) or asyncio.get_running_loop().time() >= navigation_deadline:
                        raise
                    await frame.wait_for_load_state('domcontentloaded', timeout=self.page_timeout * 1000)
                    handles = await frame.query_selector_all(selector)
                if handles:
                    if iframe:
                        self.frame = frame
                        self.facade.iframe_env = True
                    return [self.wrap_element(h) for h in handles] if many else self.wrap_element(handles[0])
            if asyncio.get_running_loop().time() >= deadline:
                if many:
                    return []
                raise NoSuchElementException(f"Element not found: {by}={value}")
            await asyncio.sleep(0.05)

    async def send_keys(self, element, values):
        from playwright_driver import Keys, _key_name
        if await element.evaluate("el => el.tagName === 'INPUT' && el.type === 'file'"):
            await element.set_input_files("\n".join(str(v) for v in values).splitlines())
            return
        await element.focus()
        pressed = []
        try:
            for value in values:
                for char in str(value):
                    if char == Keys.NULL:
                        for key in reversed(pressed):
                            await self.page.keyboard.up(key)
                        pressed.clear()
                    elif char in Keys._MODIFIERS:
                        key = _key_name(char)
                        if key not in pressed:
                            await self.page.keyboard.down(key)
                            pressed.append(key)
                    elif char in Keys._KEYS:
                        await self.page.keyboard.press(_key_name(char))
                    else:
                        await self.page.keyboard.type(char)
        finally:
            for key in reversed(pressed):
                await self.page.keyboard.up(key)

    async def element(self, key, action, *args):
        from playwright_driver import _selector, NoSuchElementException, StaleElementReferenceException
        el = self.elements[key]
        if not await el.evaluate("el => el.isConnected"):
            raise StaleElementReferenceException("Element is no longer attached to the document")
        if action == "text":
            # Native select options have no Playwright bounding box when the
            # menu is closed; their labels remain readable through WebDriver.
            option_text = await el.evaluate("el => el.tagName === 'OPTION' ? el.textContent.replace(/\\s+/g, ' ').trim() : null")
            if option_text is not None:
                return option_text
            return await el.inner_text() if await el.is_visible() else ""
        if action == "attribute":
            return await el.evaluate("""(el, name) => {
                let value = el[name];
                if (typeof value === 'boolean') return value ? 'true' : null;
                if (typeof value === 'string' || typeof value === 'number') return String(value);
                return el.getAttribute(name);
            }""", args[0])
        if action == "property":
            return await self.wrap_result(await el.get_property(args[0]))
        if action == "tag":
            return await el.evaluate("el => el.tagName.toLowerCase()")
        if action in ("click", "double_click", "hover"):
            frame = await el.owner_frame()
            fn = {"click": el.click, "double_click": el.dblclick, "hover": el.hover}[action]
            result = await self.action(fn(timeout=self.page_timeout * 1000))
            if not self.dialog and action != 'hover':
                if frame and not frame.is_detached():
                    strategy = getattr(self.facade.options, 'page_load_strategy', 'normal')
                    if strategy != 'none':
                        await frame.wait_for_load_state('domcontentloaded' if strategy == 'eager' else 'load',
                                                        timeout=self.page_timeout * 1000)
            return result
        if action == "clear":
            return await el.fill("")
        if action == "send_keys":
            return await self.action(self.send_keys(el, args))
        if action == "screenshot":
            return await el.screenshot(path=str(args[0]) if args else None)
        if action == "rect":
            return await el.bounding_box() or dict(x=0, y=0, width=0, height=0)
        if action == "displayed":
            return await el.is_visible()
        if action == "enabled":
            return await el.is_enabled()
        if action == "selected":
            return await el.evaluate("el => Boolean(el.selected || el.checked)")
        if action == "find":
            selector = _selector(args[0], args[1])
            if not selector.startswith(('xpath=', 'text=')):
                selector = 'css:light=' + selector
            handles = await el.query_selector_all(selector)
            if args[2]:
                return [self.wrap_element(h) for h in handles]
            if handles:
                return self.wrap_element(handles[0])
            raise NoSuchElementException(f"Child element not found: {args[1]}")
        if action == "select_option":
            return await self.action(el.select_option(**args[0], timeout=self.page_timeout * 1000))
        if action == "css":
            return await el.evaluate("(el, name) => getComputedStyle(el).getPropertyValue(name)", args[0])
        raise NotImplementedError(action)

    async def script(self, script, args, asynchronous=False):
        payload = {"code": script, "args": self.unwrap(args)}
        source = """p => (new Function(p.code)).apply(window, p.args)"""
        if asynchronous:
            source = """p => new Promise((resolve, reject) => {
                try { (new Function(p.code)).apply(window, [...p.args, resolve]); }
                catch(e) { reject(e); }
            })"""
        handle = await self.action(self.frame.evaluate_handle(source, payload), self.script_timeout)
        return await self.wrap_result(handle) if handle else None

    async def cdp(self, command, params):
        if command == "Page.addScriptToEvaluateOnNewDocument":
            await self.context.add_init_script(params["source"])
            return {"identifier": uuid.uuid4().hex}
        if command in ("Page.setDownloadBehavior", "Browser.setDownloadBehavior"):
            self.downloads = Path(params["downloadPath"]).resolve()
            self.downloads.mkdir(parents=True, exist_ok=True)
            return {}
        session = await self.context.new_cdp_session(self.page)
        try:
            return await session.send(command, params)
        finally:
            await session.detach()

    async def browser_logs(self):
        logs, self.logs = self.logs, []
        return logs

    async def cookie(self, action, value=None):
        if action == "get":
            return [{**c, "expiry": int(c["expires"])} if c.get("expires", -1) > 0 else c
                    for c in await self.context.cookies([self.page.url])]
        if action == "delete_all":
            return await self.context.clear_cookies()
        cookie = dict(value)
        if "expiry" in cookie:
            cookie["expires"] = cookie.pop("expiry")
        cookie.setdefault("domain", urlsplit(self.page.url).hostname)
        cookie.setdefault("path", "/")
        return await self.context.add_cookies([cookie])

    async def switch_frame(self, action, value=None):
        from playwright_driver import WebElement, NoSuchElementException
        if action == "default":
            target = self.page.main_frame
        elif action == "parent":
            target = self.frame.parent_frame or self.page.main_frame
        elif isinstance(value, WebElement):
            target = await self.unwrap(value).content_frame()
        elif isinstance(value, int):
            target = self.frame.child_frames[value]
        else:
            target = next((f for f in self.frame.child_frames if f.name == value), None)
        if target is None:
            raise NoSuchElementException(f"Frame not found: {value}")
        self.frame = target
        self.facade.iframe_env = target != self.page.main_frame

    async def window(self, handle):
        from playwright_driver import NoSuchWindowException
        page = self.pages.get(handle)
        if page is None or page.is_closed():
            raise NoSuchWindowException("Window has closed")
        self.page, self.frame = page, page.main_frame
        self.facade.iframe_env = False

    async def window_handles(self):
        return [key for key, page in self.pages.items() if not page.is_closed()]

    async def navigation(self, action, *args):
        fn = {"get": self.page.goto, "refresh": self.page.reload, "back": self.page.go_back,
              "forward": self.page.go_forward}[action]
        strategy = getattr(self.facade.options, "page_load_strategy", "normal")
        wait = {"none": "commit", "eager": "domcontentloaded"}.get(strategy, "load")
        await self.action(fn(*args, wait_until=wait, timeout=self.page_timeout * 1000))
        self.frame = self.page.main_frame
        self.facade.iframe_env = False

    async def timeout(self, kind, seconds):
        setattr(self, {"page": "page_timeout", "script": "script_timeout", "implicit": "implicit_timeout"}[kind], float(seconds))

    async def close_page(self):
        await self.page.close()

    async def read_page(self, field):
        if field == "url":
            return self.page.url
        if field == "title":
            return await self.page.title()
        if field == "content":
            return await self.frame.content()
        if field == "handle":
            return next(key for key, page in self.pages.items() if page == self.page)

    async def window_size(self, action, width=None, height=None):
        if action == "get":
            return await self.page.evaluate("({width: outerWidth, height: outerHeight})")
        session = await self.context.new_cdp_session(self.page)
        try:
            window = await session.send("Browser.getWindowForTarget")
            bounds = {"windowState": "maximized"} if action == "maximize" else {"width": int(width), "height": int(height), "windowState": "normal"}
            await session.send("Browser.setWindowBounds", {"windowId": window["windowId"], "bounds": bounds})
        finally:
            await session.detach()

    async def screenshot(self, path=None):
        return await self.page.screenshot(path=path)

    async def dialog_action(self, action, value=None):
        from playwright_driver import NoAlertPresentException
        if not self.dialog:
            raise NoAlertPresentException("No JavaScript dialog is open")
        if action == "text":
            return self.dialog.message
        if action == "prompt":
            self.prompt_text = value
            return
        dialog = self.dialog
        self.dialog = None
        self.dialog_event.clear()
        if action == "dismiss":
            await dialog.dismiss()
        else:
            await dialog.accept(getattr(self, "prompt_text", None))
        self.prompt_text = None
        if self.pending:
            await asyncio.wait(list(self.pending), timeout=self.page_timeout)

    async def keyboard(self, action, *values):
        if action == "key_down":
            return await self.page.keyboard.down(values[0])
        if action == "key_up":
            return await self.page.keyboard.up(values[0])
        element = await self.frame.evaluate_handle("document.activeElement")
        return await self.send_keys(element.as_element(), values)

    async def close_browser(self):
        if self.pending:
            for task in list(self.pending):
                task.cancel()
            await asyncio.gather(*list(self.pending), return_exceptions=True)
        if self.context and not self.attached:
            await self.context.close()
        # Stopping this connection detaches from an app-owned browser.
        await self.pw.stop()
        if self.temporary:
            self.temporary.cleanup()
