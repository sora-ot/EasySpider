# Playwright 迁移分支：npm 依赖漏洞审计

日期：2026-11-06。仓库：用户 fork `sora-ot/easyspider`，分支 `feature/playwright-migration`。

## 结论与范围

之前因 `127.0.0.1:7897` 代理拒绝连接而未完成的 **npm 审计现已成功完成**。本次通过命令级配置直连 npm 官方 registry，未修改全局代理、package.json、package-lock.json 或已安装依赖，也未执行 `npm audit fix`。

| 范围 | 严重 critical | 高危 high | 中危 moderate | 低危 low | 合计 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `npm audit --omit=dev` 生产依赖树 | 1 | 7 | 1 | 1 | 10 |
| `npm audit` 完整依赖树（包含开发工具） | 2 | 39 | 2 | 2 | 45 |

这是 npm 按受影响包名称聚合的统计，包含受传递依赖影响的上层包，**不是 45 个相互独立的漏洞**。原始结果按公告 URL 去重后，完整树涉及 66 条公告，生产树涉及 26 条；两行有包含关系，不能相加。

本次范围是 `ElectronJS/package-lock.json` 中的 Node 依赖。不是 Python/pip 全依赖审计，也不是 Chrome/Electron 二进制或操作系统扫描。`playwright-core@1.64.1` 和 `electron@45.2.3` 未出现在此次 npm 受影响包列表中，不代表已证明没有任何安全问题。

锁文件 SHA-256：`00ddb26bc18875cef501020c4dda51e1c1461a234e755656d5d0583e63190b98`。

## 生产依赖结果

| 包 | 锁定版本 | 级别 | 主要问题/影响 | npm 修复标记 |
| --- | --- | --- | --- | --- |
| `proxy-addr` | 2.0.7 | 严重 | IPv4 映射 IPv6 信任子网场景的 IP 欺骗；[公告](https://github.com/advisories/GHSA-jqcg-44mw-7w3h) | 有自动修复路径 |
| `multer` | 2.0.0 | 高危 | 多条 multipart 上传拒绝服务、资源清理和边界绕过公告；[其中一条](https://github.com/advisories/GHSA-q7qp-rjg7-q26m) | 有自动修复路径 |
| `ws` | 8.18.0 | 高危 | 小片段导致内存耗尽及未初始化内存泄漏；[公告](https://github.com/advisories/GHSA-96hv-2xvq-fx4p) | 有自动修复路径 |
| `xlsx` | 0.18.5 | 高危 | 原型污染、正则拒绝服务；[原型污染](https://github.com/advisories/GHSA-4r6h-8v6p-xvw6)、[ReDoS](https://github.com/advisories/GHSA-5pgg-2g8v-p4x9) | **无 npm 自动修复路径** |
| `body-parser` | 1.20.3 | 高危 | 压缩请求尾部数据触发拒绝服务等；[公告](https://github.com/advisories/GHSA-27r3-jxmh-p828) | 有自动修复路径 |
| `cross-spawn` | 7.0.3 | 高危 | 正则拒绝服务；[公告](https://github.com/advisories/GHSA-3xgq-45jj-v275) | 有自动修复路径 |
| `express` | 4.21.2 | 高危 | 上层依赖被标记，关联 `body-parser` 等依赖；不额外计为独立公告 | 有自动修复路径 |
| `path-to-regexp` | 0.1.12 | 高危 | 多路由参数正则拒绝服务；[公告](https://github.com/advisories/GHSA-37ch-88jc-xwx2) | 有自动修复路径 |
| `qs` | 6.13.0 | 中危 | 多条解析/序列化拒绝服务公告；[其中一条](https://github.com/advisories/GHSA-4mjr-xmp4-gh2g) | 有自动修复路径 |
| `formidable` | 3.5.0 | 低危 | 上传文件名可预测性；[公告](https://github.com/advisories/GHSA-75v8-2h7p-7m2m) | 有自动修复路径 |

“有自动修复路径”来自 npm 的 `fixAvailable` 字段，只说明依赖解析存在候选方案，不是已经升级或通过兼容性测试。`xlsx` 无自动修复路径也不等于不存在厂商新版或替代库，需要单独评估获取来源和 API 兼容性。

## 项目中的实际接触面

- `ElectronJS/server.js` 的 `/excelUpload` 实际使用 `multer` 接收文件，再用 `XLSX.readFile` 解析，所以这两项与现有功能直接有关。
- `ElectronJS/main.js` 实际使用 `ws` 提供设计器 WebSocket 服务。
- 当前 HTTP 服务和 WebSocket 均绑定 `127.0.0.1`，限制了远程直接访问，但不能据此忽略本机调用和恶意文件输入。
- 在 `main.js`、`server.js` 中没有找到 `trust proxy` 设置或 `req.ip`/`req.ips` 依赖。因此没有证据证明 `proxy-addr` 的公告触发条件已经存在于当前业务路径中；保留严重级别的依赖命中记录，不宣称成功复现漏洞。
- `formidable` 仍被 require，但查到的上传处理调用已是注释；建议核对全项目使用情况后再决定升级或移除。
- `cross-spawn` 出现在生产依赖树中，但主要关联开发启动工具。npm 的 prod/dev 分类不等同于网页请求是否能触发该代码。

本次只核对依赖公告与少量调用位置，没有对运行中的服务发送攻击载荷，也没有完成逐条漏洞可达性证明。

## 开发/打包依赖

完整树的另一项严重命中为 `tar@6.1.15`，涉及解压/解析拒绝服务和多条路径处理问题，例如 [GHSA-23hp-3jrh-7fpw](https://github.com/advisories/GHSA-23hp-3jrh-7fpw)。其他高危链包括 `extract-zip`、`lodash`、`lodash.template`、`glob`、`minimatch`、`brace-expansion`，并向上影响旧版 Forge、packager、rebuild 等包。

npm 建议部分 Forge 包升级至 8.0.1，属于跨主版本变更；对旧 `electron-rebuild` 给出的候选甚至是 2.0.3（降级）。因此不直接运行 `npm audit fix --force`：应结合当前 Electron 45 的要求选择维护中的构建工具，再重跑打包、原生模块加载和设计器联调。

只读对照了本地 `HEAD` 的锁文件：本次列出的受影响版本在该锁文件中也能找到。这说明它们并非都由 Playwright 替换引入；该对照不替代对迁移前后完整依赖树的分别审计。

## 建议修复顺序

1. 先处理实际接收输入的 `multer`、`ws` 和 Express 传递依赖，验证上传、接口、WebSocket 和设计器。
2. 为 `xlsx` 选择厂商已修复版本或替代方案；回归 Excel 导入、中文表头、日期/数值转换和多 URL 任务。
3. 协调升级 Forge/rebuild/packager，重新验证 Electron 原生模块、Python 执行器资源、扩展和 Windows 打包。
4. 更新锁文件后重跑两种审计，分别报告残留包、无法自动修复的项目和业务验证结果。

此次仅审计与记录，没有执行上述升级。

## 原始结果与复现

- [完整依赖树 JSON](audit-results/2026-11-06-npm-full.json)
- [生产依赖树 JSON](audit-results/2026-11-06-npm-production.json)

原始 JSON 已从 PowerShell 重定向的 UTF-16 转成 UTF-8，内容保持一致。以下命令在 `ElectronJS` 下运行；可以新开一个 PowerShell 窗口执行，关闭窗口后环境变量覆盖自然失效：

```powershell
$env:NO_PROXY = '*'
$env:npm_config_noproxy = '*'
npm audit --omit=dev --json --registry=https://registry.npmjs.org --proxy=null --https-proxy=null --fetch-retries=0 --fetch-timeout=15000
npm audit --json --registry=https://registry.npmjs.org --proxy=null --https-proxy=null --fetch-retries=0 --fetch-timeout=15000
```

这两次 npm 退出码为 1，原因是报告发现漏洞；并非网络请求失败。公告数据库后续更新可能改变计数。

## 两处临时解包目录

已核对以下路径是系统 TEMP 下的普通目录、不是链接，未发现从其中运行的执行器。合计 275,094,277 字节（约 262 MiB）：

- `C:\Users\张桁亿\AppData\Local\Temp\_MEI0000a1602`
- `C:\Users\张桁亿\AppData\Local\Temp\_MEI0000a3c42`

本次工具删除仍被自动审批策略拒绝，仅返回 `blocked by policy`。目录未删除，不影响审计结果。用户关闭 EasySpider 执行器后可在 PowerShell 手动执行以下精确命令，或在资源管理器打开 `%TEMP%` 后只删除这两个目录；不使用 `_MEI*` 通配符，以免影响其他程序。

```powershell
Remove-Item -LiteralPath 'C:\Users\张桁亿\AppData\Local\Temp\_MEI0000a1602', 'C:\Users\张桁亿\AppData\Local\Temp\_MEI0000a3c42' -Recurse -Force
```
