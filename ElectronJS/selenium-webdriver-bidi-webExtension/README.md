# Historical Selenium BiDi extension

This directory is retained as historical source. The Playwright migration does
not load or package it as a browser automation backend. The current designer
uses `../playwright_browser.js` and loads the EasySpider and XPathHelper MV3
extensions with Chrome's CDP `Extensions.loadUnpacked` command.
