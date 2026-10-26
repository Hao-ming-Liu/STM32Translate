# STM32 译窗

Windows 10/11 64 位离线英译中小窗，适合阅读 STM32 函数注释和参数说明。

## 开始使用

从 [GitHub Releases](https://github.com/Hao-ming-Liu/STM32Translate/releases/latest) 下载 `STM32Translate-1.0.2-win64-full.zip`（包含离线模型及运行库，无需安装 Python）。源码 ZIP 不包含模型和运行库。

1. **先完整解压 ZIP**，打开 `STM32Translate` 文件夹。
2. 双击 **STM32Translate.exe**。首次启动会显示小窗，后台留有蓝色“译”字托盘图标。
3. 在 Keil、VS Code、PDF 阅读器等软件中复制英文，按 **Ctrl+Alt+T**，自动翻译剪贴板文字。

也可以在小窗中粘贴、输入英文，点“翻译”或按 **Ctrl+Enter**。首次查询需要加载模型，后续更快。界面仅在按快捷键、粘贴或点击翻译时读取文本，不监听每次复制。

## 小窗操作

- 点击编辑器等其他窗口：自动收起。
- **固定**：保持置顶，方便对照；再次点击取消。**Esc** 始终可收起。
- **展开原文**：检查英文、修改内容；长译文在结果区滚动。
- **复制译文**：仅复制译文本身，附加的术语提示不混入剪贴板。
- **设置 → 修改快捷键**：支持 Ctrl、Alt、Shift 搭配字母、数字或 F1–F11；冲突时保留原快捷键并提示。
- 关闭按钮只收起窗口；托盘菜单或设置菜单中选择 **退出程序** 才完全退出。

## 术语记忆与联网查词

点击“联网查词”，会用输入框中的完整原文加上 `英译中（STM32）` 在默认浏览器打开 Bing 搜索，例如 `PRESENT 英译中（STM32）`。只有原文为空时才询问查询词。**浏览器查询需要联网，离线翻译不需要。**

确认中文解释后点“保存术语”，填写英文及中文即可。再次保存同名术语会更新释义；同一对话框也可删除已存词条。

单独查询已存术语时直接显示释义，不加载模型。翻译整段注释时，在结果下面显示命中的术语解释，不强行改写句子。查询网页的结果不会自动抓取或自动记忆。

首次运行附带一组 STM32 常用术语，例如 prescaler（预分频器）、pull-up resistor（上拉电阻）和 duty cycle（占空比）。它们也可以修改或删除，不会覆盖你保存过的解释。

## 离线与轻量化

- 完整包已附带英中模型，不用安装 Python，不用注册账号或填写 API 密钥。
- CPU 推理，不需要显卡或 CUDA。模型按需加载，闲置约五分钟后释放；本地术语与缓存不需要加载模型。
- 默认不开机自启；没有 OCR、语音、联网自动更新或账号同步。
- 单次最多 30000 字符。过长输入会明确提示拆分，不会静默丢弃尾部。
- Doxygen 标签、参数名、代码行尽量原样保留。正文中原先保护的术语与标识符也参与翻译，对应结果显示为红色（模型未能翻译而原样返回时也标红）；数值继续校验并保留。为准确定位颜色，术语单独翻译后放回句子，可能缺少上下文。定位失败时部分正文保留原文并提示。

这是通用离线翻译模型，专业词可能译得生硬。对照原文和保存的术语释义阅读，尤其注意否定条件、参数范围与返回值。

## 文件与故障处理

**请保持整个文件夹完整**，不要单独移动 EXE。`_internal` 是运行库，`TranslateWorker.exe` 是按需启动的隐藏翻译进程，`models` 是英中模型。

窗口位置、快捷键、术语和翻译缓存在程序旁的 `data/translator.db`。如程序目录不可写，会使用当前用户的 `%LOCALAPPDATA%\STM32Translate`。可在“设置 → 打开数据目录”查看。复制此数据库可以备份自己的词条；不随发布包分发个人数据。

快捷键已被占用时，从托盘打开窗口后修改快捷键。模型缺失时，请重新完整解压。工作进程异常退出后，下一次查询会重新启动；超时会提示拆分输入。

运行库缺失若提示 `VCRUNTIME140.dll`，请安装 Microsoft 官方 **Visual C++ 2015–2022 x64 Redistributable**：https://aka.ms/vs/17/release/vc_redist.x64.exe 。程序包内包含构建工具能收集到的运行库，本机以外的干净系统仍需实际验证。

## 源码开发

在 Python 3.12 x64 环境中：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe tools\fetch_model.py
.\.venv\Scripts\python.exe run.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tools\build.py
```

模型校验值、来源和改动见 `MODEL_INFO.json`（源码中位于 `models/en_zh/SOURCE.json`）。第三方授权见 `THIRD_PARTY_NOTICES.md` 和 `licenses`。具体实测数据与未覆盖场景见项目 `docs/verification.md`。
