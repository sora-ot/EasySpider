"""Legacy EasySpider class names backed by the Playwright browser driver."""
from playwright_driver import PlaywrightChrome, WebDriverException, By


class MyChrome(PlaywrightChrome):
    def find_element(self, by=By.ID, value=None, iframe=False):
        self.switch_to.default_content()
        return super().find_element(by, value, iframe)

    def find_elements(self, by=By.ID, value=None, iframe=False):
        self.switch_to.default_content()
        return super().find_elements(by, value, iframe)


class MyEdge:
    def __init__(self, *args, **kwargs):
        raise WebDriverException("The Playwright migration currently supports Chrome only; Edge/IE mode is unavailable")


class MyUCChrome(MyChrome):
    """Compatibility name for old task configuration; it no longer launches UC."""
    pass
