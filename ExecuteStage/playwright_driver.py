"""Synchronous EasySpider browser facade backed exclusively by Playwright."""
import threading
import json
import time
from types import SimpleNamespace



class WebDriverException(RuntimeError):
    pass


class NoSuchElementException(WebDriverException):
    pass


class TimeoutException(WebDriverException):
    pass


class StaleElementReferenceException(WebDriverException):
    pass


class InvalidSelectorException(WebDriverException):
    pass


class ElementClickInterceptedException(WebDriverException):
    pass


class JavascriptException(WebDriverException):
    pass


class NoAlertPresentException(WebDriverException):
    pass


class NoSuchWindowException(WebDriverException):
    pass


class InvalidSessionIdException(WebDriverException):
    pass


class By:
    ID = "id"
    XPATH = "xpath"
    CSS_SELECTOR = "css selector"
    NAME = "name"
    TAG_NAME = "tag name"
    CLASS_NAME = "class name"
    LINK_TEXT = "link text"
    PARTIAL_LINK_TEXT = "partial link text"


class Keys:
    NULL = "\ue000"
    BACKSPACE = "\ue003"
    TAB = "\ue004"
    RETURN = "\ue006"
    ENTER = "\ue007"
    SHIFT = "\ue008"
    CONTROL = "\ue009"
    ALT = "\ue00a"
    ESCAPE = "\ue00c"
    SPACE = "\ue00d"
    PAGE_UP = "\ue00e"
    PAGE_DOWN = "\ue00f"
    END = "\ue010"
    HOME = "\ue011"
    LEFT = "\ue012"
    UP = "\ue013"
    RIGHT = "\ue014"
    DOWN = "\ue015"
    INSERT = "\ue016"
    DELETE = "\ue017"
    F1 = "\ue031"
    F2 = "\ue032"
    F3 = "\ue033"
    F4 = "\ue034"
    F5 = "\ue035"
    F6 = "\ue036"
    F7 = "\ue037"
    F8 = "\ue038"
    F9 = "\ue039"
    F10 = "\ue03a"
    F11 = "\ue03b"
    F12 = "\ue03c"
    COMMAND = "\ue03d"
    META = "\ue03d"
    _MODIFIERS = {SHIFT: "Shift", CONTROL: "Control", ALT: "Alt", COMMAND: "Meta"}
    _KEYS = {
        NULL: "\x00", BACKSPACE: "Backspace", TAB: "Tab", RETURN: "Enter", ENTER: "Enter",
        ESCAPE: "Escape", SPACE: " ", PAGE_UP: "PageUp", PAGE_DOWN: "PageDown", END: "End",
        HOME: "Home", LEFT: "ArrowLeft", UP: "ArrowUp", RIGHT: "ArrowRight", DOWN: "ArrowDown",
        INSERT: "Insert", DELETE: "Delete", F1: "F1", F2: "F2", F3: "F3", F4: "F4",
        F5: "F5", F6: "F6", F7: "F7", F8: "F8", F9: "F9", F10: "F10", F11: "F11", F12: "F12",
    }


class ChromeOptions:
    def __init__(self):
        self.binary_location = ""
        self.page_load_strategy = "normal"
        self.arguments = []
        self.experimental_options = {}
        self.capabilities = {}
        self.extensions = []

    def add_argument(self, argument):
        self.arguments.append(str(argument))

    def add_experimental_option(self, name, value):
        self.experimental_options[name] = value

    def add_extension(self, path):
        self.extensions.append(str(path))

    def set_capability(self, name, value):
        if name == 'pageLoadStrategy':
            if value not in ('normal', 'eager', 'none'):
                raise ValueError('Unknown page load strategy: ' + str(value))
            self.page_load_strategy = value
        elif name != 'goog:loggingPrefs':
            raise ValueError('Unsupported Playwright compatibility capability: ' + name)
        self.capabilities[name] = value


class Service:
    def __init__(self, executable_path=None):
        self.executable_path = executable_path


class DesiredCapabilities:
    CHROME = {"browserName": "chrome", "pageLoadStrategy": "none"}


def _selector(by, value):
    value = str(value)
    if by in (By.XPATH, "xpath"):
        return "xpath=" + value
    if by in (By.CSS_SELECTOR, "css selector"):
        return value
    if by in (By.ID, "id"):
        return '[id=' + json.dumps(value) + ']'
    if by in (By.NAME, "name"):
        return '[name=' + json.dumps(value) + ']'
    if by in (By.TAG_NAME, "tag name"):
        return value
    if by in (By.CLASS_NAME, "class name"):
        return "." + value
    if by == By.LINK_TEXT:
        return 'a:text-is(' + json.dumps(value) + ')'
    if by == By.PARTIAL_LINK_TEXT:
        return 'a:has-text(' + json.dumps(value) + ')'
    raise InvalidSelectorException(f"Unsupported locator strategy: {by}")


def _key_name(value):
    return Keys._KEYS.get(value, Keys._MODIFIERS.get(value, value))


class PlaywrightChrome:
    """Thread-safe task API; raw Playwright objects stay in Runtime."""
    def __init__(self, service=None, options=None, mode="local_driver", endpoint=None, **kwargs):
        import asyncio
        self.options = options or ChromeOptions()
        if mode != "local_driver" or kwargs.get("command_executor"):
            raise WebDriverException("Selenium Grid URLs are not supported; use a local Chrome or an explicit CDP endpoint")
        unexpected = set(kwargs) - {"desired_capabilities", "executable_path"}
        if unexpected:
            raise TypeError("Unsupported browser options: " + ", ".join(sorted(unexpected)))
        self.iframe_env = False
        self._closed = False
        self._loop = asyncio.new_event_loop()
        self._worker = threading.Thread(target=self._serve, name="EasySpiderPlaywright", daemon=True)
        self._worker.start()
        try:
            from _playwright_runtime import Runtime
            self._runtime = Runtime(self)
            asyncio.run_coroutine_threadsafe(self._runtime.start(self.options, endpoint), self._loop).result(65)
        except BaseException:
            if hasattr(self, "_runtime") and hasattr(self._runtime, "pw"):
                try:
                    asyncio.run_coroutine_threadsafe(self._runtime.close_browser(), self._loop).result(15)
                except Exception:
                    pass
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._worker.join(15)
            raise

    def _serve(self):
        import asyncio
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()

    def _request(self, name, *args):
        import asyncio
        if self._closed:
            raise InvalidSessionIdException("The Playwright browser has been closed")
        names = {"frame": "switch_frame", "dialog": "dialog_action"}
        return asyncio.run_coroutine_threadsafe(
            self._runtime.dispatch(names.get(name, name), *args), self._loop).result()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.quit()

    def find_element(self, by=By.ID, value=None, iframe=False):
        result = self._request("find", by, value, False, iframe)
        return result if isinstance(result, WebElement) else result[0]

    def find_elements(self, by=By.ID, value=None, iframe=False):
        result = self._request("find", by, value, True, iframe)
        return result

    def find_elements_in_current_frame(self, by=By.ID, value=None):
        return self.find_elements(by, value, False)

    @property
    def current_url(self):
        return self._request("read_page", "url")

    @property
    def title(self):
        return self._request("read_page", "title")

    @property
    def page_source(self):
        return self._request("read_page", "content")

    @property
    def window_handles(self):
        return self._request("window_handles")

    @property
    def current_window_handle(self):
        return self._request("read_page", "handle")


    def get(self, url):
        return self._request("navigation", "get", url)

    def refresh(self):
        return self._request("navigation", "refresh")

    def back(self):
        return self._request("navigation", "back")

    def forward(self):
        return self._request("navigation", "forward")

    def close(self):
        return self._request("close_page")

    def quit(self):
        if self._closed:
            return
        try:
            self._request("close_browser")
        finally:
            self._closed = True
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._worker.join(timeout=15)

    def execute_script(self, script, *args):
        return self._request("script", script, list(args), False)

    def execute_async_script(self, script, *args):
        return self._request("script", script, list(args), True)

    def execute_cdp_cmd(self, command, params):
        return self._request("cdp", command, params)

    def execute(self, command, params):
        if command == "send_command":
            return self.execute_cdp_cmd(params["cmd"], params.get("params", {}))
        raise WebDriverException(f"Unsupported legacy command: {command}")

    def add_cookie(self, cookie):
        return self._request("cookie", "add", cookie)

    def get_cookies(self):
        return self._request("cookie", "get")

    def get_log(self, log_type="browser"):
        if log_type != "browser":
            return []
        return self._request("browser_logs")

    def delete_all_cookies(self):
        return self._request("cookie", "delete_all")

    def set_page_load_timeout(self, seconds):
        self._request("timeout", "page", seconds)

    def set_script_timeout(self, seconds):
        self._request("timeout", "script", seconds)

    def maximize_window(self):
        size = self.get_window_size()
        self.set_window_size(max(size["width"], 1366), max(size["height"], 768))

    def get_window_size(self):
        return self._request("window_size", "get")

    def set_window_size(self, width, height):
        return self._request("window_size", "set", width, height)

    def save_screenshot(self, path):
        self._request("screenshot", path)
        return True

    def get_screenshot_as_png(self):
        return self._request("screenshot")

    def implicitly_wait(self, seconds):
        return self._request("timeout", "implicit", seconds)



class WebElement:
    def __init__(self, driver, key):
        self._driver = driver
        self._key = key

    @property
    def text(self):
        return self._driver._request("element", self._key, "text")

    @property
    def tag_name(self):
        return self._driver._request("element", self._key, "tag")

    @property
    def id(self):
        return self._key

    @property
    def shadow_root(self):
        if not self._driver.execute_script("return !!arguments[0].shadowRoot", self):
            raise NoSuchElementException("Element has no open shadow root")
        return ShadowRoot(self)

    @property
    def screenshot_as_png(self):
        return self._driver._request("element", self._key, "screenshot")

    @property
    def location(self):
        rect = self._driver._request("element", self._key, "rect")
        return {"x": rect["x"], "y": rect["y"]}

    @property
    def size(self):
        rect = self._driver._request("element", self._key, "rect")
        return {"width": rect["width"], "height": rect["height"]}

    @property
    def rect(self):
        return self._driver._request("element", self._key, "rect")

    def is_displayed(self):
        return self._driver._request("element", self._key, "displayed")

    def is_enabled(self):
        return self._driver._request("element", self._key, "enabled")

    def is_selected(self):
        return self._driver._request("element", self._key, "selected")

    def get_attribute(self, name):
        return self._driver._request("element", self._key, "attribute", name)

    def get_property(self, name):
        return self._driver._request("element", self._key, "property", name)

    def value_of_css_property(self, name):
        return self._driver._request("element", self._key, "css", name)

    def click(self):
        return self._driver._request("element", self._key, "click")

    def clear(self):
        return self._driver._request("element", self._key, "clear")

    def send_keys(self, *values):
        return self._driver._request("element", self._key, "send_keys", *values)

    def find_element(self, by=By.ID, value=None):
        result = self._driver._request("element", self._key, "find", by, value, False)
        return result if isinstance(result, WebElement) else result[0]

    def find_elements(self, by=By.ID, value=None):
        return self._driver._request("element", self._key, "find", by, value, True)

    def screenshot(self, path):
        self._driver._request("element", self._key, "screenshot", path)
        return True

    def _select_option(self, **kwargs):
        return self._driver._request("element", self._key, "select_option", kwargs)


class ShadowRoot:
    def __init__(self, host):
        self.host = host

    def find_elements(self, by=By.ID, value=None):
        if by in (By.XPATH, By.LINK_TEXT, By.PARTIAL_LINK_TEXT):
            raise InvalidSelectorException("Shadow root lookup supports CSS-based locators")
        return self.host._driver.execute_script(
            "return Array.from(arguments[0].shadowRoot.querySelectorAll(arguments[1]))",
            self.host, _selector(by, value))

    def find_element(self, by=By.ID, value=None):
        elements = self.find_elements(by, value)
        if not elements:
            raise NoSuchElementException(f"Element not found in shadow root: {value}")
        return elements[0]


class _SwitchTo:
    def __init__(self, driver):
        self.driver = driver

    def default_content(self):
        return self.driver._request("frame", "default")

    def parent_frame(self):
        return self.driver._request("frame", "parent")

    def frame(self, frame_reference):
        return self.driver._request("frame", "switch", frame_reference)

    def window(self, handle):
        return self.driver._request("window", handle)

    @property
    def alert(self):
        return _Alert(self.driver)


class _Alert:
    def __init__(self, driver):
        self.driver = driver

    @property
    def text(self):
        return self.driver._request("dialog", "text")

    def accept(self):
        return self.driver._request("dialog", "accept")

    def dismiss(self):
        return self.driver._request("dialog", "dismiss")

    def send_keys(self, value):
        return self.driver._request("dialog", "prompt", value)


PlaywrightChrome.switch_to = property(lambda self: _SwitchTo(self))


class Select:
    def __init__(self, element):
        self.element = element

    @property
    def options(self):
        return self.element.find_elements(By.TAG_NAME, "option")

    @property
    def first_selected_option(self):
        for option in self.options:
            if option.is_selected():
                return option
        raise NoSuchElementException("No selected option")

    @property
    def all_selected_options(self):
        return [option for option in self.options if option.is_selected()]

    def select_by_visible_text(self, text):
        return self.element._select_option(label=text)

    def select_by_value(self, value):
        return self.element._select_option(value=value)

    def select_by_index(self, index):
        return self.element._select_option(index=int(index))


class ActionChains:
    def __init__(self, driver):
        self.driver = driver
        self.actions = []

    def move_to_element(self, element):
        self.actions.append(("hover", element))
        return self

    def click(self, element=None):
        self.actions.append(("click", element))
        return self

    def double_click(self, element=None):
        self.actions.append(("double_click", element))
        return self

    def key_down(self, key):
        self.actions.append(("key_down", key))
        return self

    def key_up(self, key):
        self.actions.append(("key_up", key))
        return self

    def send_keys(self, *keys):
        self.actions.append(("send_keys", keys))
        return self

    def perform(self):
        for action, value in self.actions:
            if action in ("hover", "double_click") and value is not None:
                self.driver._request("element", value._key, action)
            elif action == "click":
                if value is None:
                    self.driver.execute_script("document.activeElement.click()")
                else:
                    value.click()
            elif action in ("key_down", "key_up"):
                self.driver._request("keyboard", action, _key_name(value))
            elif action == "send_keys":
                self.driver._request("keyboard", "send_keys", *value)
        self.actions.clear()


class WebDriverWait:
    def __init__(self, driver, timeout, poll_frequency=0.2, ignored_exceptions=(NoSuchElementException,)):
        self.driver = driver
        self.timeout = float(timeout)
        self.poll_frequency = float(poll_frequency)
        self.ignored_exceptions = ignored_exceptions

    def until(self, method, message=""):
        deadline = time.monotonic() + self.timeout
        last_error = None
        while time.monotonic() < deadline:
            try:
                value = method(self.driver)
                if value:
                    return value
            except self.ignored_exceptions as exc:
                last_error = exc
            time.sleep(self.poll_frequency)
        raise TimeoutException(message or str(last_error or "Condition was not met before timeout"))

    def until_not(self, method, message=""):
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                if not method(self.driver):
                    return True
            except self.ignored_exceptions:
                return True
            time.sleep(self.poll_frequency)
        raise TimeoutException(message or "Condition remained true until timeout")


class _ExpectedConditions:
    @staticmethod
    def presence_of_element_located(locator):
        return lambda driver: driver.find_element(*locator)

    @staticmethod
    def visibility_of_element_located(locator):
        def condition(driver):
            element = driver.find_element(*locator)
            return element if element.is_displayed() else False
        return condition

    @staticmethod
    def element_to_be_clickable(locator):
        def condition(driver):
            element = driver.find_element(*locator)
            return element if element.is_displayed() and element.is_enabled() else False
        return condition

    @staticmethod
    def title_contains(value):
        return lambda driver: value in driver.title

    @staticmethod
    def url_contains(value):
        return lambda driver: value in driver.current_url


EC = _ExpectedConditions
Options = ChromeOptions
webdriver = SimpleNamespace(Chrome=PlaywrightChrome, ChromeOptions=ChromeOptions)
