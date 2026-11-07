# Selenium → Playwright 迁移与回归记录

日期：2026-11-06。默认浏览器：项目自带 Google Chrome。本文先于实现建立，测试结果随实施更新；“计划测试”不等于“已通过”。

## 仓库与边界

- EasySpider：用户 fork `sora-ot/easyspider`，本地分支 `feature/playwright-migration`。
- AI 原型：独立仓库 `sora-ot/ai-rpa-prototype`，同名本地分支。它被主仓库忽略，必须独立保存、检出。
- 不向上游 `NaiboWang/EasySpider` 推送或修改；上游 issue 仅作为公开只读的回归需求来源。
- 工作树原有修改保留。发布目录 `.temp_to_pub`、已编译 exe、用户 Profile/任务和历史反检测报告不作为新源码测试的替代。

## 影响分析

| 模块/功能 | Selenium 耦合与风险 | 迁移策略与验收 |
| --- | --- | --- |
| Python 多线程执行器 | 主线程创建浏览器、任务线程使用；Playwright sync 对象不能跨线程 | 浏览器专属工作线程，所有 Playwright 对象只在此线程访问；测跨线程、多实例、关闭与异常传播 |
| `myChrome.py` / 浏览器启动 | ChromeDriver、Remote/Grid、IE、UC 特殊模式、启动参数 | 项目级 Playwright API 适配；使用随包 Chrome；明确拒绝不兼容的 Grid/IE，UC 不再作为后端 |
| 定位与提取 | XPath、相对 XPath、多元素、text/property/attribute、stale、隐藏元素、head 数据 | 保留任务 JSON 和定位语义；递归 iframe 搜索及恢复主 frame；测缺失、非法 XPath、DOM 替换 |
| 点击/输入/动作 | Ctrl/Command+A、回车、组合键、双击、悬停、select、上传 | Playwright 键盘/鼠标/元素操作；测受控输入事件、select 的 change、确认框、文件选择 |
| 等待/导航 | 显式等待、page/script timeout、导航中断、返回、刷新、多个 URL | 保留超时异常语义及节点等待；测动态 DOM、失败 URL 后继续、history、多 tab |
| 标签与弹窗 | Selenium handle、switch_to、alert | 稳定 page 标识、frame 上下文；测试 popup 发现、切换/关闭、confirm accept/dismiss |
| JavaScript/自定义 Python | arguments 中传元素、async callback、返回 DOM element；用户脚本直接访问 browser | 兼容项目实际使用的 API；公开兼容范围，任意第三方 Selenium 脚本不保证兼容 |
| Cookies/Profile/登录 | 用户信息复制、cookie 域/expiry、localStorage、人工登录 | persistent context；隔离测试资料目录，测试重启持久化与 cookie 属性 |
| 下载/截图/OCR | CDP 下载路径、下载重命名线程、元素截图、PNG | 映射下载配置，验证内容/文件名与截图可解码；保留业务输出逻辑 |
| Electron 设计器 | Node Selenium API、BiDi 扩展安装、XPathHelper、录制 WS | Node Playwright 适配；用 Chrome 支持的扩展接口实测加载，不假定新 Chrome 允许旧命令行参数 |
| 设计器连接边界 | 8084 WebSocket cookie 导出、本机监听 | 保留 loopback 监听；新 AI CDP 连接校验 Profile、端点及所属进程。现有 cookie 消息未发现 token 鉴权，不声称此问题已解决 |
| AI agent / observer / debugger / editor | 独立浏览器、页面观察/截图、元素候选、列表试采、登录闸门 | 共用明确版本的浏览器适配契约；保留脱敏、预算、schema 和 task grounding；真实浏览器 fixture + mock LLM |
| AI native_bridge | 扫描 ChromeDriver 端口并附加 WebDriver session；HTTP 多线程 | 改为只连接 EasySpider 发布的本机设计器端点，核对 Profile；detach 不关闭用户浏览器 |
| 旧入口/依赖/打包 | single executor、custom code、requirements、spec、npm/build scripts、ChromeDriver 检查 | 活跃入口移除 Selenium 运行依赖；打包携带 Playwright driver；旧已编译 exe 必须重新构建才获得迁移 |
| 跨平台/远程/反检测 | Windows/macOS/Linux 差异；Grid 与 CDP 协议不同 | 本机 Windows Chrome 验证；未运行平台明确标未测。Playwright 迁移不等于反检测能力提升，不作网站通关保证 |

## 已关闭 issue → 回归设计

关闭不代表已修复；以下按症状设计可重复的本地用例，不把第三方站点变化当成框架错误。

| 上游 issue | 症状 | 测试 |
| --- | --- | --- |
| [986](https://github.com/NaiboWang/EasySpider/issues/986) | cookie 导出缺鉴权 | 审查并保留本机监听；校验新增 CDP 端点边界。现有 cookie 消息鉴权仍是独立遗留问题，本次未实现或验证 token 认证 |
| [880](https://github.com/NaiboWang/EasySpider/issues/880)、[961](https://github.com/NaiboWang/EasySpider/issues/961) | 新 Chrome 插件不加载 | 实际 Chrome 151 加载中/英文录制扩展与 XPathHelper；验证扩展页面/脚本 |
| [246](https://github.com/NaiboWang/EasySpider/issues/246)、[623](https://github.com/NaiboWang/EasySpider/issues/623)、[79](https://github.com/NaiboWang/EasySpider/issues/79) | nested/dynamic iframe | 两层 iframe、兄弟 frame、跨源 frame、等待后查找、查找后主页面恢复 |
| [268](https://github.com/NaiboWang/EasySpider/issues/268) | 列表分页和详情循环重复 | 列表相对 XPath、分页内容变化、详情新 tab 后恢复、输出行次序 |
| [163](https://github.com/NaiboWang/EasySpider/issues/163) | select 后 confirm | select 触发 change、accept/dismiss；弹窗不死锁 |
| [185](https://github.com/NaiboWang/EasySpider/issues/185) | 自定义代码上传 | input[type=file] send_keys 路径、文件名及内容 |
| [542](https://github.com/NaiboWang/EasySpider/issues/542)、[911](https://github.com/NaiboWang/EasySpider/issues/911) | headless/UC/Profile | 有头/无头启动、持久 Profile、废弃模式提示、退出清理 |
| [335](https://github.com/NaiboWang/EasySpider/issues/335)、[203](https://github.com/NaiboWang/EasySpider/issues/203)、[236](https://github.com/NaiboWang/EasySpider/issues/236) | 路径/启动/权限 | 中文和空格路径、非项目 cwd、缺失浏览器报错；macOS/Linux 需后续实机 |
| [639](https://github.com/NaiboWang/EasySpider/issues/639)、[581](https://github.com/NaiboWang/EasySpider/issues/581) | 登录状态复用/人工登录 | cookie/localStorage 重启保留；登录闸门、取消、超时、同 Profile 互斥 |
| [374](https://github.com/NaiboWang/EasySpider/issues/374)、[150](https://github.com/NaiboWang/EasySpider/issues/150)、[211](https://github.com/NaiboWang/EasySpider/issues/211) | head/自定义 JS/页面脚本 | DOM attributes、脚本前后处理、元素参数和结构化返回值 |
| [251](https://github.com/NaiboWang/EasySpider/issues/251) | 多 URL 中断 | URL 有序执行、错误后继续、退出与窗口状态 |

## 测试层次与判定标准（实现前设计）

1. **现有单元回归基线**：主项目输出名、JSON 追加、MySQL 配置、预处理、下载图片、控制台编码；AI `test_*.py` 的 workflow/observer/auth/editor/native bridge 等。不调用付费模型，不访问用户任务/登录信息。
2. **浏览器契约测试**：本机临时 HTTP 服务提供表单、异步 DOM、iframe、popup、dialog、download/upload、cookie、列表分页。对旧后端可运行的共同契约先采基线；新后端同时验证异常、DOM 句柄和跨线程行为。
3. **执行器业务测试**：真实任务图覆盖 open/input/select/click/hover/extract/loop/condition/custom/wait，断言输出值、行顺序和导航恢复，避免仅测试包装函数是否被调用。
4. **设计器与 AI 联动**：实际扩展安装；Node/Python 共用同一 Chrome 时互相可见，detach 后 Node 仍可操作；观察候选→编辑任务→真实浏览器回放；错误 Profile/陈旧 observation/越权端点拒绝。
5. **依赖与交付**：源文件编译、Node 语法检查、活跃源码中 Selenium import 审计、PyInstaller/打包配置检查。跨平台和所有外网真实站点不在本机可穷尽范围内。

每次失败保留可定位的原因，修复后重新运行相关测试。报告最终列出精确命令、数量、结果、未验证范围，不能以“无异常”替代行为断言。

## 实施结果

### 实现方式

迁移覆盖主执行器、single 兼容入口、Electron 设计浏览器，以及独立 AI 原型的探索、观察、调试和原生连接。Python 新增 `ExecuteStage/playwright_driver.py` 与 `_playwright_runtime.py`，Node 新增 `ElectronJS/playwright_browser.js`。

为保留现有任务图、XPath 和自定义脚本中实际使用的接口，适配层仍提供 `find_element`、`execute_script`、`switch_to`、`Select`、`ActionChains` 等名称；这些方法内部调用 Playwright，不启动 Selenium 或 ChromeDriver。Python 的 Playwright 对象全部归专属 asyncio 线程所有，执行器线程和 AI HTTP/调试线程通过队列式调用访问。两个 Python 项目共用同一实现，原型需与主项目的迁移分支配套使用。

设计器加载解包后的中/英文 EasySpider 扩展和 XPathHelper MV3，使用 Chrome 的 `Extensions.loadUnpacked`。新版本 Chrome 下必须从 Playwright 默认参数中移除 `--disable-extensions`；只获得扩展 ID 并不能证明内容脚本运行，因此测试还实际打开 XPathHelper、输入 XPath 并检查高亮结果。

AI 原生连接改为读取选定 Profile 中的 `.easyspider-playwright.json`，只接受指定版本、EasySpider 标识、匹配的 Profile、本机 WebSocket CDP 地址和合法进程。Windows 下检查所属进程为 Electron/EasySpider。连接结束只断开自己的 Playwright 连接，不关闭设计器的 Chrome。

### 验证环境

- Windows x64；Conda `easyspider`，Python 3.11。
- 采集/设计 Chrome：`ElectronJS/chrome_win64/chrome.exe`，151.0.7922.76。
- Python `playwright==1.64.1`、Node `playwright-core@1.64.1`。
- Electron 从 27.1.3 升至 45.2.3：旧内嵌 Node 18 不满足当前 Playwright 的 Node 20+ 要求。开发主机 Node 24.14.1，Electron 内嵌 Node 24.22.2。
- `node-abi` 升至 3.101.0，可识别 Electron 45 的 ABI 150；Forge/rebuild 依赖已解析至同一版本。Electron 内加载 Playwright 及 Windows 窗口管理原生模块已实测。
- 本次均使用本机 fixture、临时 Profile 和模拟模型；没有调用付费模型或用用户真实账号进行采集。

### 已通过的测试

下表每一行独立计数；不要将 Python 7 项浏览器测试再加到包含它们的 58 项中。

| 测试 | 结果 | 行为断言 |
| --- | --- | --- |
| 主仓库 `unittest discover -s scripts -p 'test_*.py' -q` | 58/58 | 原有 51 项输出名/JSON/MySQL/预处理等回归，加 7 项真实 Chrome 契约 |
| `scripts/test_playwright_driver.py` | 7/7，已包含在上行 | XPath/相对定位、输入组合键、select 文字/change/confirm、双击/悬停、嵌套跨源 iframe、popup、cookie/Profile、下载内容、上传内容、PNG、异步 JS 与 DOM 返回值、stale/非法 XPath、日志、两浏览器跨线程、移动端 |
| AI 原型 `unittest discover -s tests -p 'test_*.py' -q` | 129/129 | workflow、观察脱敏、登录闸门、编辑器、原生存储/连接、端点验证；迁移前基线为 126 |
| `scripts/test_playwright_designer.js` | 通过 | 真实 Chrome 输入/组合键、下拉框、确认/取消、悬停/双击、frame、popup、cookie、表单导航 |
| `scripts/test_xpath_helper_bidi.js` | 中/英文均通过 | 历史文件名保留；实际使用 Playwright/CDP，验证扩展脚本、XPath 匹配数和元素高亮 |
| `scripts/test_electron_runtime.js` | 通过 | Electron 45 实际运行、Playwright 加载、Windows 原生窗口模块可调用 |
| `scripts/smoke_electron_package.js` | Windows x64 包后端通过 | 使用项目已有 electron-packager、缓存的 Electron 45 构建隔离包；包内实际加载 Playwright/原生模块，启动随包 Chrome、安装扩展并输入；不复制用户任务/Profile |
| AI `tests/smoke_browser.py`、`ui_smoke.py` | 均通过 | 模拟模型的输入/点击/列表试采/任务生成；设置、两轮澄清、确认和预览 |
| AI `tests/flowchart_browser_smoke.py` | 通过 | 真实流程图循环/分支、只读预览、AI 确认、同 ID 更新及恢复 |
| AI `tests/editor_browser_smoke.py --require-discovery` | 通过 | 真 Electron 设计器、手工保存、节点调试、AI 确认、DOM 绑定、同 ID 写回、刷新、断开后重连 |
| AI `tests/debugger_browser_smoke.py` | 通过 | 观察→候选字段修改→高亮→输入/提取试运行，拒绝过期观察，关闭后重开 |
| AI `tests/layered_observation_browser.py`、`multimodal_smoke.py` | 均通过 | 大 DOM 分层读取/补充候选/脱敏/生成流程；模拟多模态调用与真实 PNG |
| AI `tests/executor_smoke.py` | 主源码、single 旧 `--id` 入口与 Windows exe 均通过 | 实际执行 input→click→三页循环，校验 6 条记录内容和顺序；启动日志必须标识 Playwright |
| AI `tests/list_grounding_browser.py --native` | 两种布局均通过 | 普通卡片和自定义元素包裹的卡片，各三页 36 条；排除骨架屏、隐藏副本 |
| `benchmark_design/tests/browser_smoke.py` | S01–S10，10/10 | 参考浏览器操作与 fixture 独立判定 |
| `benchmark_design/tests/browser_extended_smoke.py` | S11–S28，18/18 | iframe、shadow DOM、跨域 popup、详情返回、控件、503、冷却/阻断、多关键词、下载、合并表格、大 DOM 等 |

最后两行是浏览器参考脚本，不是 AI 自主完成 28 个任务的成功率，也不是反检测分数。复杂 AI→任务图→exe 用例与最终产物信息在下方补充。

### 复杂业务回放与产物

`ai-rpa-prototype/tests/complex_cases.py` 让模拟模型通过真实 agent 工具边界操作本机网页，再把生成的任务图交给打包执行器。以下每个场景均逐字段校验结果，日志必须包含 `Browser backend: Playwright`。

| 场景 | 内容 | 结果 |
| --- | --- | --- |
| T1 | 三页商品列表，逐条进入详情页后返回；合并标题、价格、库存、SKU | 6 条准确记录，通过 |
| T2 | 列表中的新标签页详情，关闭后恢复列表；缺失日期使用默认值 | 5 条准确记录，通过 |
| T3 | 输入两个关键词，选择分类，分别分页后去重 | 7 条准确记录，通过 |
| T4 | 滚动加载更多内容，排除广告节点 | 4 条准确记录，通过 |
| T5 | Excel 多 URL 输入、条件/重试流程、JSON 导出 | 3 条准确记录，通过 |
| T6 | 模拟人工登录，持久 Profile 交给原生执行器，列表及详情采集 | 6 条准确记录，通过；账号密码未写入任务图 |
| T5 + `--fault temporary_503` | 第二个 URL 首次返回 503，实际触发重试 | 恢复后 3 条完整记录，通过 |
| T5 + `--fault persistent_503` | 第二个 URL 持续返回 503，重试三次后继续后续 URL | 两条有效记录加一条明确错误记录，通过；未把失败页面当成成功数据 |
| T6 + `--fault session_expires --recover` | 第二页登录过期；重新登录后以同一任务 ID 重跑 | 过期时保留首批 3 条，重新登录后准确得到完整 6 条，通过 |
| T1 + `--fault detail_login` | 列表公开、详情页要求登录，试采触发人工登录闸门后重新探索 | 登录事件确实触发，原生执行器复用 Profile 得到 6 条完整记录，通过 |

Windows x64 完整执行器已用 PyInstaller 6.22.1 构建，保留 pandas/OCR 依赖，包含 Playwright driver 数据。最终 exe 已单独通过三页 6 条记录的端到端验证，再复制到 `ElectronJS/chrome_win64/easyspider_executestage.exe`。源码和测试入口的 `EASYSPIDER_TEST_EXECUTOR` 可分别选择源码、single 入口或该 exe。

- 构建产物：`ExecuteStage/build_playwright/dist/easyspider_executestage.exe`，157,146,281 字节。
- 构建产物与 Chrome 目录中的 exe 的 SHA-256 均为 `451FEBB55CCC1BB9EDA1FD1F88EEEDFEF0CBED23347D4AD069384FDE43B6B3D1`。
- 迁移前本地 exe 备份：`ExecuteStage/build_playwright/backup/easyspider_executestage-before-playwright-20261106191504.exe`。
- 构建过程目录和日志已忽略，不作为源码提交；源码仓库仍有迁移前的用户改动，因此本次没有把整个工作树提交或推送。两个仓库均处于 `feature/playwright-migration`，改动仍在各自工作树中。
- Chrome 目录本来就在 `ElectronJS/.gitignore` 中，因此本机更新的 exe 不会随 Git 源码自动传递；其他机器需要按照构建脚本重新生成执行器。
- Electron 烟测产物：`ExecuteStage/build_playwright/electron-package-3utdEU/EasySpider-win32-x64`。这是用于验证打包依赖和浏览器资源的隔离包，未执行正式发布脚本或安装器制作；真实设计器 UI 的完整联调结果来自源码运行。

### 发现并修正的兼容差异

1. Playwright 同步对象不能跨线程：改为专属 asyncio 线程，保留执行器和 AI 的调用模型。
2. 元素点击后的加载/导航时序不同：在动作前取得所属 frame，并按任务加载策略等待；页面导航销毁上下文时正确转换 stale 异常。
3. 原生 select 的 option 没有可见矩形，但 Selenium 可读取其文字：专门保留 option 标签文字，覆盖 AI 选择选项的校验路径。
4. `confirm` 会阻塞点击/select：动作与 dialog 事件协同，让调用方可以 accept/dismiss，避免互相等待。
5. 自定义 JS 可以返回 DOM 对象或在返回时已发生导航：分别处理 JSON/元素与 primitive，避免无必要的二次页面求值。
6. Playwright CSS 默认穿透 shadow DOM：Python 普通 CSS 查询保留原边界，显式 `shadow_root` 访问独立支持。
7. 下载线程可能看到未写完的文件：先保存为 `.crdownload` 临时文件，完成后原子替换，再由原下载重命名逻辑处理。
8. 旧测试通过 AST 抽取执行器方法，其命名空间不含新启动辅助函数：只更新测试夹具，保留 MySQL/输出文件的实际行为测试。
9. 复杂场景的旧模拟模型读取了已不再向模型提供的 XPath：改用现有语义候选和 `first_record_of`，不扩大模型的数据边界。
10. 并行启动多个完整 PyInstaller 单文件程序时，系统临时盘空间不足造成解包失败：后续复测使用 G 盘测试临时目录，降低并发；这类失败不计为浏览器功能通过。

测试环境的两处失败解包残留位于 `%TEMP%/_MEI0000a1602` 和 `%TEMP%/_MEI0000a3c42`，共 275,094,277 字节。自动审批策略拒绝清理这两处目录（仅返回 `blocked by policy`），因此保留原状；不影响 G 盘测试结果。`npm audit` 最初因本机代理 `127.0.0.1:7897` 拒绝连接而失败，随后使用命令级直连配置成功完成：完整树 45 个受影响包，生产树 10 个，本次只审计、未升级依赖。详见[依赖漏洞审计报告与删除说明](DEPENDENCY_AUDIT_2026-11-06.md)。

### 复现入口

主仓库中运行：

```powershell
conda activate easyspider
python -X utf8 -m unittest discover -s scripts -p 'test_*.py' -q
node scripts/test_playwright_designer.js
node scripts/test_xpath_helper_bidi.js
ElectronJS/node_modules/electron/dist/electron.exe scripts/test_electron_runtime.js
node scripts/smoke_electron_package.js  # Windows x64；需要已缓存的 Electron 安装包
```

AI 原型仓库中运行：

```powershell
python -X utf8 -m unittest discover -s tests -p 'test_*.py' -q
python -X utf8 tests/executor_smoke.py
python -X utf8 tests/editor_browser_smoke.py --require-discovery
python -X utf8 tests/debugger_browser_smoke.py
python -X utf8 tests/list_grounding_browser.py --native
python -X utf8 tests/complex_cases.py t1  # t1 至 t6 分别运行
python -X utf8 benchmark_design/tests/browser_smoke.py
python -X utf8 benchmark_design/tests/browser_extended_smoke.py
```

`executor_smoke.py` 默认验证源码；环境变量 `EASYSPIDER_TEST_EXECUTOR` 指定新构建 exe 后验证打包后端。`run_native.py` 和复杂用例使用 `ElectronJS/chrome_win64/easyspider_executestage.exe`，并通过 `EASYSPIDER_CHROME_BINARY`、`EASYSPIDER_DATA_DIR` 指定浏览器和隔离数据目录，无需旧 ChromeDriver 路径或目录连接。系统临时盘不足时，可仅对测试进程设置 `TEMP`/`TMP` 为有空间的临时目录。

### 兼容范围与未验证项

- 当前默认且已验证的是本机 Windows x64 Chrome。Linux、macOS、Windows 32 位没有实机验证；当前 Python Playwright 依赖也不能视为旧 32 位 Python 的直接替代。
- Selenium Grid/Remote WebDriver URL、IE/Edge 专用启动路径、旧 `cloudflare=1`/undetected-chromedriver 模式不兼容，明确报错。普通 Chrome 路径保留原有 stealth 注入，但没有承诺 Cloudflare 通关或反检测提升。
- 适配层覆盖本项目使用的 API，不是全部 Selenium API 的实现。用户自定义代码若直接 `import selenium`、操作 `command_executor`、创建 WebDriver session 或依赖未实现的方法，需单独改写。旧任务 JSON 的常规节点无需格式迁移。
- `easyspider_executestage_single.py` 转发至维护中的主执行器，并将 `--id` 转成 `--ids`；不再维护独立旧引擎。
- 旧 UC 源码、历史 BiDi 扩展目录和反检测报告仅为历史材料，不被新运行入口导入。`.temp_to_pub` 与旧发行包未同步；启动旧包仍可能运行 Selenium。
- 已验证 Python Windows 单文件构建及运行，以及 Electron Windows 隔离包内的浏览器后端。未验证正式 Forge make、完整安装器、签名、更新流程或打包后全部 UI；Electron 主版本升级后的全部操作系统集成行为尚不能由本机测试穷尽。
- OCR、实际 MySQL 服务、代理认证、下载重名的并发压力、用户所有既有网站/脚本尚未全面实测。已有测试通过不构成“所有网页零回归”的保证。
- 本次未重跑 Selenium/Playwright 的同条件外部反检测对照测试，不能根据迁移成功推断检测率改善。
