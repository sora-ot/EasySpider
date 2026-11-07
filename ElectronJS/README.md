## 视频教程

[从源代码编译程序并设计运行和调试任务指南（基于Ubuntu24.04）](https://www.bilibili.com/video/BV1VE421P7yj/)

# 环境编译说明 | Environment Compilation Instruction

EasySpider分三部分：

1. 主程序：在`ElectronJS`文件夹下。
2. 浏览器扩展：在`Extension`文件夹下，为浏览器的“操作台”的代码，打包后的扩展在此目录下的`EasySpider_zh.crx`文件。
3. 执行阶段程序：在`ExecuteStage`文件夹下。

此部分为`主程序`的编译说明。

-----

EasySpider is divided into three parts:

1. Main program: Located in the ElectronJS folder.
2. Browser extension: Located in the Extension folder, i.e., the `EasySpider_en.crx` file in this folder.
3. Execution stage program: Located in the ExecuteStage folder.

This section covers the compilation instructions for the `main program`.


## 建议编译顺序 | Suggested Compilation Order

1. 准备解包后的 `EasySpider_zh`、`EasySpider_en` 和 `XPathHelper_MV3` 扩展目录；Playwright 设计器直接加载这些目录。
2. 编译主程序，此时主程序可以正常运行，但无法执行任务，只能设计任务。
3. 编译执行阶段程序，否则无法执行任务，只能设计任务。

-----

1. Prepare the unpacked `EasySpider_zh`, `EasySpider_en` and `XPathHelper_MV3` directories, which the Playwright designer loads directly.
2. Compile the main program, at this time the main program can run normally, but can not execute the task, can only design the task.
3. Compile the execution stage program, otherwise the task cannot be executed, can only design the task.

## 注意事项 | Note

扩展更新时同步解包目录；执行器更新时重新构建 `easyspider_executestage`。旧 exe 不会因 Python 源码变化而自动更新。

Update the unpacked extension directories and rebuild `easyspider_executestage` whenever their source changes.

## 环境构建 | Environment Setup

以下以Windows x64版本为例。

Taking the example of Windows x64 version.

### Chrome (Playwright)

This branch uses Playwright with the bundled Google Chrome. Install Python dependencies
from `ExecuteStage/requirements.txt` and run `npm install` in this directory.
Electron 45 downloads its binary explicitly: after installing packages, run
`node node_modules/electron/install.js` once before starting the app.
Node.js 22.12+ is required by Electron 45; use Node.js 24 LTS for development.

To copy an installed Chrome into the project, run `python update_chrome.py`.
Use `--source <installation-directory>` if Chrome is installed elsewhere.
The updater retains existing executors and copies the platform launcher and `stealth.min.js`.
It does not download ChromeDriver. The supported bundle locations are:

```
chrome_win64/chrome.exe
chrome_linux64/chrome
chrome_mac64.app/Contents/MacOS/Google Chrome
```

The designer loads the unpacked EasySpider and XPathHelper MV3 extensions through CDP.
Use a current Chrome supporting `Extensions.loadUnpacked` (Chrome 151 was tested).
The Python executor accepts `EASYSPIDER_CHROME_BINARY` to override its browser path.
Rebuild the execution stage before running generated tasks: an old executable still
contains its old browser backend. See [migration and test results](../Docs/PLAYWRIGHT_MIGRATION.md).
Windows 32-bit and old Windows/Electron releases are not a validated Playwright target.

### NodeJS环境 | NodeJS Environment

1. Windows环境下需要先下载`VS Build Tools 2017` （[https://aka.ms/vs/15/release/vs_buildtools.exe](https://aka.ms/vs/15/release/vs_buildtools.exe)）并勾选安装其中的`Visual C++ Build Tools（Visual C++生成工具）`组件以便`node-gyp`模块来安装`node-windows-manager`，不然下面的命令无法执行，其他系统不需要。同时，`Python3`也需要安装在系统中并配置好环境变量。
2. 安装`NodeJS`：[https://nodejs.org/zh-cn/download/](https://nodejs.org/zh-cn/download/)。
3. 运行下面的命令来安装依赖：

```
npm install
```

如果上面的命令运行速度很慢可以参考使用NodeJS和Electron包的换源说明来加速安装：[https://blog.csdn.net/qq_38463737/article/details/140277803](https://blog.csdn.net/qq_38463737/article/details/140277803)。

-----

1. On Windows, you need to download `VS Build Tools 2017` (https://aka.ms/vs/15/release/vs_buildtools.exe, select and install the `Visual C++ Build Tools` component) first for the module `node-gyp` to install `node-windows-manager` (No need for other OS). Meanwhile, `Python3` needs to be installed and the environment variables need to be configured.
2. Install `NodeJS`: [https://nodejs.org/en/download/](https://nodejs.org/en/download/).
3. Run the following commands to install NodeJS packages:

```
npm install
```

## 运行说明 | Run Instruction

在当前文件夹执行以下命令即可在开发模式下运行程序：

```sh
npm run start_direct
```

但到此为止只能设计任务，不能执行任务，想要执行任务还需要完成`ExecuteStage`文件夹下的执行任务程序的编译说明才可以执行。

-----

Run the software in developing mode:

```sh
npm run start_direct
```

But so far can only design the task, can not execute the task, want to execute the task also need to complete the 'ExecuteStage' folder of the execution of the task program compilation instructions can be executed.

## 打包发布说明 | Package Instruction

打包发布前，确保执行阶段程序`easyspider_executestage(.exe)`已放入`chrome(_win64)`文件夹内，且浏览器插件`EasySpider_zh.crx`已经是最新版本。

执行下面的命令即可打包（需要安装`Git`）：

```
npm run package
```

-----

Before packaging and releasing, make sure that the task execution program `easyspider_executestage(.exe)` is placed inside the `chrome(_win64)` folder and that the browser extension `EasySpider_en.crx` is the latest version. 

After finishing developing, package software by the following command (`Git` is required):

```
npm run package
```

### For windows x64

依次执行下面两个cmd即可打包并发布，无需执行上面的npm命令，其他系统同理。

```
package_win64.cmd
clean_and_release_win64.cmd
```

-----

Execute the following two CMD commands sequentially to package and publish the program. There is no need to execute the previous npm command. The process is similar for other systems.

```
package_win64.cmd
clean_and_release_win64.cmd
```

## 可能出现的问题 | Troubleshooting

以下命令一般不需要执行，但打包时可能会用到：

```sh
npm install @electron-forge/cli -g
npx electron-forge import
```

如果任务执行到`npm install electron-squirrel-startup`的步骤时卡死，请参考下面的换源教程：[https://blog.csdn.net/qq_38463737/article/details/140277803](https://blog.csdn.net/qq_38463737/article/details/140277803)。

Windows端如果在运行`npm run package`的时候提示`node-gyp`相关的错误，可以安装`electron-rebuild`并重新编译相关模块：

```sh
npm install --save-dev electron-rebuild
npx electron-rebuild
```

然后再次运行`npm run package`。

-----

The following commands are generally not required, but may be used during packaging:

```sh
npm install @electron-forge/cli -g
npx electron-forge import
```

If the task is stuck at the `npm install electron-squirrel-startup` step, please refer to the following tutorial on changing the source: [https://blog.csdn.net/qq_38463737/article/details/140277803](https://blog.csdn.net/qq_38463737/article/details/140277803).

If you encounter `node-gyp` related errors when running `npm run package` on Windows, you can install `electron-rebuild` and recompile the relevant modules:

```sh
npm install --save-dev electron-rebuild
npx electron-rebuild
```

Then run `npm run package` again.

