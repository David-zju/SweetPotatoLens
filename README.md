# Sweet Potato Lens

Sweet Potato Lens 是一个针对小红书网页端开发的自动化搜索与信息提取脚本。该工具结合了 Playwright 的网页自动化功能与大语言模型（LLM/VLM）的文本解析功能，用于提取和汇总小红书笔记信息。

由于部分小红书笔记以图片为主要内容载体，本项目支持通过配置选项，触发视觉大模型（VLM）对笔记图片进行解析，以提取图中的文字内容。

## 功能列表

*   **Cookie 复用**: 通过前置脚本扫码保存浏览器状态，支持后续执行时的自动化免登录访问。
*   **并发提取**: 使用 Playwright 异步 API，支持同时发起多个搜索请求并提取多篇笔记内容。
*   **Prompt 解析**: 调用 LLM 将用户的初始输入解析为 1-3 个相关的搜索关键词。
*   **条件图像解析**: 提供字数阈值配置项。当笔记正文字数低于设定阈值时，自动下载首图并调用视觉大模型（如 Qwen-VL）提取图内文字。
*   **API 兼容性**: 网络请求基于 OpenAI Python SDK 实现。支持本地运行的 Ollama 模型，也支持通过修改配置文件接入支持兼容 API 的其他大语言模型服务（如 DeepSeek、通义千问等）。
*   **Markdown 导出**: 包含配置项，可将模型生成的最终汇总内容输出为本地的 Markdown 文件。

## 使用说明

### 1. 安装依赖

运行本项目需要 Python 3.8 或以上环境。

```bash
# 安装必要的 Python 包
pip install -r requirements.txt

# 下载 Playwright 依赖的 Chromium 浏览器
playwright install chromium
```

### 2. 生成登录凭证

初次使用前，需运行登录脚本获取并保存本地登录状态：

```bash
python login_xhs.py
```
> 运行上述命令后，浏览器界面将打开。请使用移动端小红书 APP 扫码登录。当页面完全加载至首页后，返回终端按下回车键。程序将在同级目录生成 `xhs_state.json` 文件。

### 3. 修改配置文件

在项目目录下编辑 `config.json` 文件：

```json
{
  "api_base": "http://localhost:11434/v1",  // API 基础路径，默认指向本地 Ollama 端口
  "api_key": "ollama",                      // API 密钥，使用本地 Ollama 时可随意填写
  "model_name": "qwen3.5:35b",              // 文本处理及总结所用的模型名称
  "vision_model_name": "qwen3-vl:32b",      // 图像解析所用的多模态模型名称
  "enable_vision": false,                   // 是否开启图像内容解析功能
  "vision_text_threshold": 100,             // 触发图像解析的正文字数阈值 (仅 enable_vision 为 true 时生效)
  "num_notes_to_fetch": 3,                  // 针对每个关键词，需提取的笔记数量
  "headless_browser": true,                 // 是否在无界面模式下运行浏览器
  "default_prompt": "西湖一日游必去景点与美食",   // 默认提示词
  "save_summary_to_file": true              // 运行结束后是否在本地生成 .md 格式的报告
}
```

*注：若需切换为云端 API（例如 DeepSeek），请将 `api_base` 更改为 `https://api.deepseek.com/v1`，填入对应的 `api_key`，并修改 `model_name`。*

### 4. 运行主程序

依赖环境与配置确认无误后，执行主脚本：

```bash
python agent.py
```

程序启动后，将提示输入需要搜索的内容。随后程序将依次执行关键词生成、并发抓取、条件图像解析（如已开启）以及最终内容汇总。运行结果将打印在控制台中，并根据配置决定是否保存为 Markdown 文件。

## MCP 服务集成

本项目支持模型上下文协议 (Model Context Protocol, MCP)。通过配置，可将本工具直接接入支持 MCP 的 AI 客户端（如 Claude Desktop, Cursor 等）。

在 MCP 模式下，本服务仅负责提取小红书的图文原始数据并返回给客户端。**生成搜索词和最终内容总结的工作将由你的 AI 客户端（如 Claude）自行完成。**

### 配置方法 (以 Claude Desktop 为例)

1. **安装 MCP 依赖**:
   ```bash
   pip install mcp
   ```

2. **验证登录凭证**:
   请确保已至少运行过一次 `python login_xhs.py`，并在项目根目录下存在 `xhs_state.json` 文件。

3. **修改客户端配置**:
   打开 Claude Desktop 的 MCP 配置文件（通常位于 `%APPDATA%\Claude\claude_desktop_config.json`），添加以下配置。**请务必替换为你本地真实的 Python 路径和项目路径**：

   ```json
   {
     "mcpServers": {
       "SweetPotatoLens": {
         "command": "C:/path/to/your/python.exe",
         "args": [
           "C:/path/to/your/Dev/xhs-agent/mcp_server.py"
         ]
       }
     }
   }
   ```

4. **使用工具**:
   重启客户端后，在对话框输入“帮我在小红书搜索xxx”，客户端便会自动调用此工具收集数据。

### MCP 模式功能说明

*   **智能能力自省与图文协同**: 本工具在 MCP 模式下具备一项独特的高级特性。在客户端 LLM（如 Claude、GPT-4o）调用此工具时，工具会要求其进行能力自省。如果客户端 LLM 评估自己具备原生读取 Base64 格式图像的能力，它便可声明 `client_supports_vision=True`。随后，爬虫会自动识别那些“以图为主、文本极少”的笔记，并在后台帮大模型把图片下载好、转码成 Base64 打包在 JSON 返回值中，由客户端大模型亲自提取图内信息。这样不仅能最大化利用前端高级大模型（如 Claude 3.5 Sonnet）的识图能力，也免去了客户端无法访问小红书防盗链图片的痛点。
*   **运行状态不可见问题**: MCP 模式运行在系统后台，默认不会在控制台打印进度。如果需要观察抓取时的实际动作，可在 `config.json` 中将 `"headless_browser"` 改为 `false`。
*   **响应速度调整**: 如果客户端调用时等待时间过长，可通过在 `config.json` 中调低 `num_notes_to_fetch`，或将 `"enable_vision"` 设置为 `false` 来加快数据返回速度。