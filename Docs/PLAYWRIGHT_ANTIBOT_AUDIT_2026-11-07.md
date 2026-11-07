# EasySpider Playwright 反检测复测报告

测试日期：2026-11-07（Asia/Shanghai）
测试分支：`feature/playwright-migration`
浏览器：项目随包 Chrome 151，Playwright persistent context，有头模式，临时 Profile。
## 测试范围

本轮使用公开检测页面和一个本地稳定探针，比较 Playwright 迁移后的当前配置与增强配置。公开页面包括：

- [Rebrowser Bot Detector](https://bot-detector.rebrowser.net/)
- [BrowserScan Bot Detection](https://www.browserscan.net/bot-detection)
- [Brotector](https://ttlns.github.io/brotector/?crash=false)
- [MickeyJS](https://mickeyalton33.github.io/MickeyJS/)
- [CreepJS](https://abrahamjuliot.github.io/creepjs/)
- [BrowserLeaks JavaScript](https://browserleaks.com/javascript)
- [Incolumitas](https://bot.incolumitas.com/)

脚本入口为 [`scripts/playwright_antibot_audit.js`](../scripts/playwright_antibot_audit.js)。脚本记录页面摘要和本地指纹，不记录公网 IP。Brotector 在本轮仍会因为注入栈触发页面自身的递归异常，因此保留该原始错误，不能把它解释为通过或失败分数。

## 当前 Playwright 配置基线

迁移后的 Electron 设计器已经使用 `stealth.min.js`、`--disable-blink-features=AutomationControlled` 和持久 Profile。Python 执行器也保留了原有 stealth 注入。AI-RPA 原型此前没有统一继承这些设置。

基线的稳定探针结果为：

| 指标 | 基线 |
|---|---|
| `navigator.languages` | `['en-US', 'en']` |
| Worker languages | `['zh-CN', 'zh']` |
| `hardwareConcurrency` | 4 |
| Worker hardwareConcurrency | 16 |
| `navigator.webdriver` | undefined/删除 |
| `window.cdc_*`、`window.wdc_*` | 未发现 |
| 时区 | `Asia/Shanghai` |

基线的主要公开结果：Rebrowser 标红 `runtimeEnableLeak`、`navigatorWebdriver`、`nativeTampering` 和 `workerConsistency`；BrowserScan 总体为 `Robot`，但其 Selenium/WebDriver 子项在 Playwright 设计器链路中已经不是 Selenium 命中；MickeyJS 仍给出 `100/100 automated`；CreepJS 约 `80% stealth`；Incolumitas 暴露主页面与 Worker 指纹不一致。

## 已实施的增强

增强逻辑集中在共享启动层：

1. 主页面、iframe 和 Worker 使用同一 locale；默认 `zh-CN` 对应 `['zh-CN', 'zh']`。
2. stealth 脚本的固定 `hardwareConcurrency: 4` 改为主机实际逻辑核数，或由 `EASYSPIDER_HARDWARE_CONCURRENCY` 显式配置。
3. Playwright Python 和 Electron 启动统一使用 `--lang`、`locale` 和 `timezoneId`。
4. 移除 Playwright 默认的 `--disable-popup-blocking` 和 `--disable-ipc-flooding-protection`，使弹窗和 history API 行为更接近普通 Chrome。
5. `navigator.webdriver` 仅在仍然存在时修改原型 getter，避免在 `navigator` 实例上创建 own property。
6. AI-RPA 的 `agent.py` 和 `debugger.py` 通过 `antidetect_config.py` 继承同一套配置。

## 增强配置实测结果

本地稳定探针：

```json
{
  "language": "zh-CN",
  "languages": ["zh-CN", "zh"],
  "hardwareConcurrency": 16,
  "worker": {
    "languages": ["zh-CN", "zh"],
    "hardwareConcurrency": 16
  },
  "ownWebdriver": false,
  "cdcGlobals": [],
  "timezone": "Asia/Shanghai",
  "platform": "Win32"
}
```

公开检测摘要：

| 检测器 | 增强后结果 | 变化和限制 |
|---|---|---|
| Rebrowser | `popupBlocking` 正常；`ipcFloodingProtection` 正常；`platformMismatch` 正常；Worker 一致 | 仍标红 CDP `runtimeEnableLeak`、缺失 webdriver 和 `nativeTampering` |
| BrowserScan | 总体仍可能显示 Robot；WebDriver/Selenium 子项为 Normal | 页面仍可能依据其他自动化信号给出总体判断 |
| MickeyJS | `100/100 automated`；仍识别 CDP、Playwright 和原生函数代理 | 这是专门的 CDP/自动化侧信道探测，当前架构仍会暴露 |
| Brotector | 页面注入栈触发 `Maximum call stack size exceeded` | 不能将异常当作通过；栈中仍可看到 stealth 代理 |
| CreepJS | 约 `80% stealth` | 指纹一致性改善，但它没有单一 Selenium 通过分数 |
| BrowserLeaks | JavaScript 页面正常加载，未给出统一 bot 分数 | 用于观察浏览器指纹，不是自动化判定器 |
| Incolumitas | Worker navigator 一致性为 `OK`；Service Worker 一致性仍为 `FAIL`；旧 `WEBDRIVER` 项仍为 `FAIL` | 行为分数需要完成页面挑战，本轮未填写挑战 |

## 解释与边界

这次增强确实改善了可测量的指纹一致性，并消除了部分 Playwright 默认开关造成的异常。它不能保证绕过 Cloudflare、验证码或任何具体站点的风控。现代检测器仍可以通过 CDP Runtime、调试通道、被代理的原生函数、`navigator.webdriver` 缺失以及行为轨迹识别自动化。

因此不建议继续随机修改 UA、WebGL、屏幕尺寸或大量原生 API。更可靠的方向是：使用真实 Chrome 和持久 Profile，保持 UA、Client Hints、locale、时区、Worker/Service Worker 一致；对需要 Native Bridge 的 Electron 设计器接受 CDP 暴露；对不需要调试附加的执行链路避免额外调试端口，并在上线前用同一组检测页面做回归。
