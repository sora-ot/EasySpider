# EasySpider Selenium 反检测能力检测报告

| 项目 | 值 |
|---|---|
| 检测日期 | 2026-11-06（Asia/Shanghai） |
| 检测对象 | EasySpider 当前工作树中的 Selenium 浏览器配置 |
| 浏览器 | 项目随包 Chromium/Chrome 151.0.7922.76，ChromeDriver 151.0.7922.76 |

## 结论摘要

当前的反检测设置可以隐藏或弱化部分常见标记，例如 `navigator.webdriver` 和无头特征，但不能消除 Selenium/CDP 的运行痕迹，也没有把各个浏览器指纹维持在一致状态。本次实测中，BotD 在 Python 执行器和 Electron 设计器两条链路上都明确返回 `bot: true, botKind: "selenium"`；Brotector 检出了 `window.cdc_*` 自动化全局和 Selenium/stealth 注入栈；Rebrowser Bot Detector 在 Python 链路上标红多个项目。

CreepJS 和 BrowserLeaks 没有给出可直接横向比较的统一“反检测分数”，但观察到了语言、CPU 核数等指纹差异。由此可以判断 EasySpider 当前配置属于“部分隐藏、仍可被多类检测识别”，不能据此推断所有网站都会拦截，也不能当作 Playwright 的对比测试。

## 检测环境与复现方式

本次使用项目随包浏览器和驱动，而不是连接用户日常 Chrome：

| 项目 | 值 |
|---|---|
| Conda 环境 | `easyspider` |
| Python | 3.11.14 |
| Python Selenium | 4.47.0 |
| Electron Selenium WebDriver | 4.27.0 |
| Chrome / ChromeDriver | 151.0.7922.76 / 151.0.7922.76 |
| 浏览器模式 | 有头模式；每项测试使用隔离的临时 Profile |

Python 执行器路径依据 [easyspider_executestage.py](../ExecuteStage/easyspider_executestage.py#L2442)：排除 `enable-automation` 开关，添加 `--disable-blink-features=AutomationControlled` 等项目参数；浏览器启动后通过 CDP 注入随包的 `stealth.min.js`，并额外把 `navigator.webdriver` 改为返回 `undefined`，见 [初始化代码](../ExecuteStage/easyspider_executestage.py#L169)。检测没有使用现有用户 Profile、Cookie 或登录态。

Electron 设计器路径依据 [main.js](../ElectronJS/main.js#L1546)：开启 WebDriver BiDi，排除 `enable-automation`、关闭自动化扩展，并安装 EasySpider 与 XPathHelper MV3 两个扩展；之后通过 `executeScript` 覆写 `navigator.webdriver`，再用 Selenium `Script.pin` 注入 `stealth.min.js`，见 [浏览器初始化代码](../ElectronJS/main.js#L1623)。检测使用当前工作树中的扩展文件。

对 Rebrowser、Brotector、CreepJS、BrowserLeaks 与 BotD 分别启动独立会话。BotD 使用其公开 v2 CDN，在 HTTPS 页面调用 `load({monitoring:false}).detect()`。BrowserLeaks 结果中的公网 IP 未写入本文；该页面所报告的地址已从记录中遮蔽。

## 检测结果

### Rebrowser Bot Detector

检测页：[bot-detector.rebrowser.net](https://bot-detector.rebrowser.net/)

页面展示自动化相关的运行时、Navigator、Worker、原生函数、视口、网络加载和浏览器版本检查。检测器中的绿色只表示对应项目未发现异常；白色表示该项尚未被触发或没有结果，不计为通过。

**Python 执行器配置：**

| 页面项目 | 结果 | 观察到的内容 |
|---|---|---|
| `runtimeEnableLeak` | 红 | 页面认为有自动化环境启用 CDP Runtime 或序列化 Console 参数的信号。 |
| `navigatorWebdriver` | 红 | `navigator.webdriver` 为 `undefined`；检测页将删除/隐藏该属性视为可疑。 |
| `nativeTampering` | 红 | 页面报告 `Navigator.languages`、`Navigator.hardwareConcurrency`、WebGL `getParameter`、`Function.toString`、`navigator.webdriver` 等属性/函数被代理或覆写；还报告 iframe 的 `contentWindow` 与父窗口共享 Realm。 |
| `popupBlocking` | 黄 | 页面观察到未由用户点击触发的弹窗受到阻止。 |
| `workerConsistency` | 黄 | 主页面与 Worker 指纹不一致：主页面 `languages=["en-US","en"]`、CPU 核数 4；Worker 为 `languages=["zh-CN","zh"]`、CPU 核数 16。 |
| `viewport`、`platformMismatch`、`mobileEmulation`、`documentInterception`、`ipcFloodingProtection`、`cdpBindingGlobals`、`headless`、CSP、`storagePartitioning`、`useragent` | 绿 | 此次检测中这些项目未报告异常；UA 与 Client Hints 的 Chrome/Windows 信息匹配，无头检测未命中。 |
| 其他白色项目 | 未触发 | 不能作为通过结果。 |

在同一 Python 会话中按页面提示显式触发了额外诊断：`dummyFn` 为绿，`sourceUrlLeak` 为绿，`mainWorldExecution` 为红。后者说明 Selenium 注入脚本在页面 Main World 执行。`sourceUrlLeak` 虽为绿，页面采集到的调用栈仍包含 Selenium `executeScript`，但没有判定为可疑 sourceURL。

**Electron 设计器配置：** 重新使用实际 BiDi 启动参数、安装两个项目扩展并注入 stealth 脚本后，页面报告 `runtimeEnableLeak` 为红、`popupBlocking` 为黄；`navigatorWebdriver`、`workerConsistency`、`nativeTampering`、`headless`、`platformMismatch` 等为绿。另在页面脚本中直接枚举到 `window.cdc_adoQpoasnfa76pfcZLmcfl_*` 自动化全局；这说明单个检测器子项为绿并不代表没有其他可观察信号。设计器测试页面中也出现了 EasySpider 的采集操作台，确认扩展确实加载。

检测页在本次运行时报告最新 Stable Chrome 为 158.0.8127.18（页面给出的发布日期为 2026-11-04），项目随包 Chrome 为 151.0.7922.76。版本差距是浏览器指纹背景信息，不单独视为自动化命中。

### Brotector

检测页：[ttlns.github.io/brotector](https://ttlns.github.io/brotector/?crash=false)。此前提及的旧地址 `kaliiiiiiiiii.github.io/brotector` 当前返回 404，因此改用此可访问页面。

页面顶部 `Average` 项显示 `score=1.00`，检测记录中包括：

- `window.cdc`：发现多项 `cdc_adoQpoasnfa76pfcZLmcfl_*` 全局变量。
- `stack.signature`：检测栈中出现 `SeleniumScriptInjectionHandler` 和脚本包装器调用；页面将其中若干记录归到 `puppeteerPluginStealth` 类型。这个类型标签描述的是它匹配到的注入/包装栈特征，不代表本次使用了 Puppeteer。

在隔离会话中页面本身成功加载，但 Selenium 读取 `current_url` 时复现 `Runtime.callFunctionOn threw exception: RangeError: Maximum call stack size exceeded`。随后通过 Chrome DevTools Protocol 的 `Runtime.evaluate` 读取页面内容成功。该异常可能与页面脚本或 WebDriver 命令交互有关，本次证据不足以断言是检测页刻意造成。

### CreepJS

检测页：[abrahamjuliot.github.io/creepjs](https://abrahamjuliot.github.io/creepjs/)。等待页面异步指纹计算完成后读取结果。它提供多项指纹和熵信息，没有单一的 Selenium 通过/失败分数。

本次页面显示：

- 指纹摘要区域出现 `80% stealth`，并将 `extension` 标记为 `puppeteer-extra`。这是页面对浏览器特征的归类，不是对 EasySpider 所用自动化框架的准确产品识别。
- 主页面的 `navigator.languages` 为 `en-US, en`，但 Worker 语言为 `zh-CN`；页面时区为 `Asia/Shanghai`。
- 主页面报告 `hardwareConcurrency=4`，Worker 报告 16。
- 页面采集到 Chrome 151、Windows、屏幕尺寸、字体、Canvas、WebGL、Audio 等指纹。Chrome UA 的 Windows NT 10.0 字符串与 User-Agent Client Hints 中的 Windows 11/平台版本信息也同时呈现；这类差异需要结合 Chrome 的 UA Reduction 和操作系统判断，本文不单独把它算作自动化命中。

### BrowserLeaks

检测页：[JavaScript Browser Information](https://browserleaks.com/javascript) 与 [WebRTC Leak Test](https://browserleaks.com/webrtc)。BrowserLeaks 是浏览器、网络和 API 指纹诊断集合，不提供统一的 Selenium bot 分数。

JavaScript 页面观察到 `navigator.webdriver=undefined`，`navigator.language=zh-CN`，但 `navigator.languages=["en-US","en"]`；时区是 `Asia/Shanghai`，`hardwareConcurrency=4`，UA/Client Hints 显示 Chrome 151。页面同时枚举了插件、Battery、Bluetooth、SpeechSynthesis 等浏览器 API 信息。这些是可用于构成指纹的属性；页面本身没有给出统一的自动化判定。

WebRTC 页面显示 WebRTC API 可用、**No Local IP Leak**，同时报告页面所见 WebRTC IP 与远端 IP 不匹配。为保护网络隐私，公网地址没有记录在报告中。此项是网络路径诊断结果，不等于 Selenium 检测结果。

### BotD

检测库：[BotD v2 CDN](https://openfpcdn.io/botd/v2)。在 HTTPS 页面动态导入 BotD，关闭持续监控后调用 `detect()`。

| 浏览器链路 | 返回值 |
|---|---|
| Python 执行器配置 | `{"bot": true, "botKind": "selenium"}` |
| Electron 设计器配置（含 BiDi、两个扩展及 stealth 注入） | `{"bot": true, "botKind": "selenium"}` |

这是本次测试中最直接的 Selenium 分类结果。它只代表 BotD v2 当前检测逻辑在本机测试会话中的判断，不代表所有反机器人系统都会采用相同逻辑。

## 综合判断与限制

`excludeSwitches`、`AutomationControlled` 参数和 `navigator.webdriver` 覆写确实让部分页面检查呈绿，但不能遮蔽所有 CDP、WebDriver、注入栈及全局对象痕迹。Python 执行器对原生 API 的覆写也形成了新的不一致信号；设计器链路在部分 Rebrowser 子项上更干净，但 BotD 仍明确分类为 Selenium。

这是一台 Windows 机器上的单次检测，没有做原生 Chrome 基线、Playwright A/B 对照或多轮统计。检测站点会更新规则，结果受 Chrome 版本、系统语言、硬件、网络和页面版本影响。本次 Electron 设计器使用的是当前工作树里的扩展文件；如果本地扩展有尚未提交的修改，结果可能与仓库干净版本不同。结论应理解为对本机当前配置的实测快照，而非对所有 EasySpider 部署环境的保证。

## 补充自动化检测器实测（2026-11-06）

本轮补测针对 Python 执行器的 Selenium 启动配置：项目随包 Chrome/ChromeDriver 151.0.7922.76，有头模式，使用 `excludeSwitches=['enable-automation']`、`--disable-blink-features=AutomationControlled`、项目 `stealth.min.js` 和 `navigator.webdriver` 覆写。BrowserScan、MickeyJS、Incolumitas 各使用独立临时 Profile。此轮没有重新启动 Electron 设计器链路，因此结果应与前文 Electron 的 Rebrowser/BotD 结果分开解读。报告没有记录检测页显示的公网 IP。

### BrowserScan Bot Detection

检测页：[BrowserScan Bot Detection](https://www.browserscan.net/bot-detection)。页面版本区域显示 `1.4.1.0`，结果如下：

| 检测项 | 页面结果 |
|---|---|
| 总体 `Test Results` | `Robot` |
| `WebDriver` | `Robot` |
| `WebDriver Advance` | `Normal` |
| `Selenium` | `Robot` |
| `Chrome DevTools Protocol` / `CDP` | `Normal` |
| `Headless Chrome` | `Normal` |
| NightmareJS、PhantomJS、Webdriverio 等其他分类 | `Normal` |

页面同时展示 Native Navigator 的 `webdriver`、语言、CPU 核数、UA、插件和 Client Hints 等字段。这个结果说明隐藏 `navigator.webdriver` 和无头特征并没有阻止 BrowserScan 对 WebDriver/Selenium 的分类命中；CDP 子项为 `Normal` 也不能抵消 WebDriver 与 Selenium 两项的明确命中。

### MickeyJS

检测页：[MickeyJS](https://mickeyalton33.github.io/MickeyJS/)。该页面声称运行 31 项客户端探针，覆盖 CDP 侧信道、栈特征、跨 Realm 一致性、输入事件和反检测篡改。

首次扫描结果：`100/100 automated`，`13 signals`，`3 definitive`，31/31 探针运行完成。页面的归因包括：

- `Anti-detect patching`：7 个信号，100%；
- `Selenium / ChromeDriver`：1 个信号，100%；
- `CDP client attached`：4 个信号，83%；
- `DevTools open (human)`：3 个信号，70%。

页面列出的确定性证据包括 `cdc_/wdc_` ChromeDriver 属性名模式、内置函数表现为包装函数，以及主页面与 Worker 的 Navigator 不一致。页面还报告 `navigator.webdriver` 被重新定义/缺失等环境信号。

随后尝试在页面提示的交互区域执行移动、点击、滚动和输入，并触发重新扫描。Selenium 的坐标操作部分返回 `MoveTargetOutOfBoundsException`，但页面仍记录了 2 次移动、1 次点击和 1 次 raw pointer 更新；重新扫描结果仍为 `100/100 automated`，信号增至 14 个、确定性信号增至 4 个，并新增 `ChromeDriver automation bundle executing in the page`。因此交互操作异常没有改变“明确被识别为自动化”的结论。

MickeyJS 的分数是该项目自己的证据聚合，不应与 BotD 或 Rebrowser 的分数直接相加；但它给出的 Selenium/ChromeDriver 归因和 ChromeDriver 全局变量证据，与 BrowserScan、Brotector 的结果方向一致。

### Incolumitas Bot / Headless Chrome Detection Tests

检测页：[bot.incolumitas.com](https://bot.incolumitas.com/)。页面自标版本为 `0.6.3 (6th June 2024)`，属于检测集合和测试索引，不是单一算法，因此保留页面原始字段名称。

本次等待约 30 秒后，行为分类仍显示 `Your Behavioral Score: ...`，没有产生数值；页面说明完整行为评分需要完成其公开的表单挑战，本次没有提交该挑战。因此不能把行为评分缺失解释成通过或失败。

页面的新版检测字段中出现：

- `inconsistentWebWorkerNavigatorPropery: FAIL`；
- `inconsistentServiceWorkerNavigatorPropery: FAIL`；
- `webDriver: true`；
- `nightmareJS: false`，并且其 `selenium` 数组中的若干单项为 `false`。

页面同时列出旧版测试字段：`webDriver: OK`、`webDriverAdvanced: OK`、`WEBDRIVER: FAIL`、`SELENIUM_DRIVER: OK`。这些字段来自不同历史测试模块，页面没有给出统一的 OK/FAIL 语义，不能把它们压缩成一个“通过率”；结合同页的 `webDriver: true` 和 Worker/Service Worker 不一致结果，应以具体字段和原始证据为准。

该页面还报告 TCP/IP 指纹的 `os_mismatch: true` 和 `flagged: true`，并提示 IP API 数据不完整。公网 IP 和相关地址没有写入报告；这些属于网络/传输路径诊断，不能单独归因于 Selenium。

### 本轮增补结论

BrowserScan 和 MickeyJS 都对当前 Python Selenium 会话给出了明确的自动化命中，其中 MickeyJS 还直接归因为 Selenium/ChromeDriver 并记录了 ChromeDriver 注入证据。Incolumitas 进一步暴露了主页面、Worker 和 Service Worker 之间的指纹不一致，但其行为评分未完成，且部分页面字段较旧、语义混杂。三者与前文 BotD、Brotector、Rebrowser 的结果共同表明：EasySpider 当前 Selenium 配置能隐藏少数表层字段，却仍然暴露 WebDriver/ChromeDriver 全局、脚本注入、CDP/调试通道和跨 Realm 指纹不一致等信号。
