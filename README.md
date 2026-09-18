# autoSolve × OCS 本地适配器

这是一个面向本地环境的 OCS 非官方适配项目：为 OCS 提供统一的题目处理接口，并在用户已经获准访问的超星页面中解码页面下发的混淆字体。项目默认启用“只保存、不自动提交”，便于人工核对结果。

> 本项目不是 OCS 官方发行版，与 OCS、超星学习通、DeepSeek 及相关学校或平台不存在隶属、授权或背书关系。

## 功能范围

- 提供原生接口 `POST /api/v1/solve` 和 OCS 兼容接口 `POST /api/ocs/solve`；
- 兼容 OCS 的 `AnswererWrapper` 请求结构；
- 提供 `POST /api/ocs/font/decode`，用本地字形指纹解析超星页面内嵌字体；
- 支持浏览器会话 provider、DeepSeek 官方 API provider 和禁用 provider；
- 日志不记录密码、Cookie 或题目正文；
- 修改版 OCS 默认开启安全模式，章节测试只保存答案，不自动提交。

字体解码思路参考 [chaoxing_solution_of_font_confusion](https://github.com/TellMeYourWish/chaoxing_solution_of_font_confusion)。OCS 的安装和配置概念请以 [OCS 官方文档](https://docs.ocsjs.com/) 与 [AnswererWrapper 开发文档](https://docs.ocsjs.com/docs/other/api) 为准。

## 工作方式

```text
已授权访问的课程页面
        │
        ├─ 题目、题型、选项 ──> /api/ocs/solve ──> provider
        │
        └─ 页面内嵌字体 + 页面实际字符
                         └────> /api/ocs/font/decode
                                      │
                                本地字形指纹比对
```

字体接口只要求字体中“本页实际使用且属于该字体 cmap”的字符全部解出。普通中文不会被误报成加密字符；只要仍有字体覆盖字符无法识别，OCS 就会停止后续答题流程。

## 安装

要求 Python 3.10 或更高版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
```

启动本地服务：

```powershell
python server.py
```

默认监听 `http://127.0.0.1:8080`。健康检查地址为 `http://127.0.0.1:8080/health`。

## 安装修改版 OCS

1. 在 ScriptCat 或 Tampermonkey 中停用其他同名 OCS 脚本，避免两个版本同时运行。
2. 导入仓库根目录的 `OCS刷题脚本.js`。
3. 在“通用 → 全局设置”中选择“autoSolve”答题接口。
4. 保持“安全模式（禁止自动提交）”开启；发布版默认值已经开启。
5. 确认接口地址为 `http://127.0.0.1:8080/api/ocs/solve`。

脚本通过 `GM_xmlhttpRequest` 访问本机接口，元信息仅放行 `localhost`、`127.0.0.1` 以及 OCS 上游原有域名。不要为了省事将 `@connect` 改为 `*`。

## Provider 配置

项目不自动读取 `.env` 文件；请在启动进程的终端中设置环境变量，或由你自己的进程管理器注入。可参考 `.env.example`。

### 浏览器会话（默认）

```powershell
$env:AUTOSOLVE_PROVIDER = "browser"
$env:AUTOSOLVE_BROWSER_HEADLESS = "false"
python server.py
```

首次请求会打开浏览器，请手动登录。登录状态保存在 `browser-profile/`，该目录可能包含敏感会话数据，已被 `.gitignore` 排除，禁止上传或分享。

### DeepSeek 官方 API（可选）

```powershell
$env:AUTOSOLVE_PROVIDER = "deepseek"
$env:DEEPSEEK_API_KEY = "你的密钥"
python server.py
```

不要把密钥写入源码、README、Issue 或提交记录。API 使用及费用受服务提供方条款约束。

### 禁用解题 provider

```powershell
$env:AUTOSOLVE_PROVIDER = "disabled"
python server.py
```

禁用后解题接口返回 HTTP 503；字体解码接口仍可独立使用。

## 接口摘要

### `POST /api/ocs/solve`

```json
{
  "title": "下面哪项正确？",
  "type": "single",
  "options": "A. 甲\nB. 乙",
  "interface": "ocs"
}
```

答案位于响应的 `data[0].answer`。旧配置可以使用兼容入口 `POST /api/search.php`。

### `POST /api/ocs/font/decode`

```json
{
  "font_base64": "页面内嵌字体的 Base64 内容",
  "used_codepoints": [21751, 21752]
}
```

服务返回 Unicode 码点映射、字体标识、缓存状态以及未解析码点。接口只应接收当前授权页面已经下发给浏览器的字体数据。

### 诊断与日志

- `GET /api/v1/diagnostics`：provider、接口和字体资产状态；
- `logs/autosolve.log`：轮转日志，单文件上限 5 MiB，保留 3 个备份；
- `AUTOSOLVE_LOG_LEVEL=DEBUG`：提高日志级别；
- `AUTOSOLVE_CAPTURE_DEBUG=true`：显式允许浏览器异常截图，输出到 `debug-artifacts/`。

## 测试

```powershell
python -m pytest -q
node --check .\OCS刷题脚本.js
```

`scripts/test_browser_chat.py` 是需要人工登录的集成测试，不会被 `pytest` 自动执行。

## 合规与可接受使用

本项目的文档和免责声明不能替任何使用方式自动取得合法性。是否合法取决于适用法律、学校规定、课程要求、平台协议、账号授权范围和实际用途。使用者至少应遵守以下边界：

- 只处理本人账号有权访问的页面与数据，不绕过登录、付费、权限控制、验证码、限流或其他访问控制；
- 仅用于本地兼容性研究、无障碍阅读、个人学习辅助、题目格式整理，或经课程/平台明确允许的自动化测试；
- 不用于代学、替考、未授权批量访问、计分作业或考试作弊，也不传播账号、Cookie、题目库或其他受保护内容；
- 使用自动生成的答案前必须人工核对。安全模式只是减少误提交风险，不保证答案正确，也不替代课程规则；
- 如平台、学校或课程禁止自动化，应立即停用本项目；如有疑问，应先取得书面授权。

项目不会修改平台服务器源码，也不提供绕过身份认证的能力。它仍会自动处理浏览器已经取得的数据，因此使用者必须确保自己的处理行为获得授权。

## 开源、署名与第三方材料

本仓库原创的 Python 适配代码按 `LICENSE` 中的 MIT License 提供。`OCS刷题脚本.js` 是基于 [ocsjs/ocsjs](https://github.com/ocsjs/ocsjs) 的修改版，上游采用 MIT License；原作者、许可证声明和上游链接均予保留。

字形指纹数据参考并包含来自 `chaoxing_solution_of_font_confusion` 的兼容性资产。该参考仓库当前页面未显示明确许可证，公开发布前应由发布者确认这些二进制数据的再分发授权；未取得授权时，应移除相关资产并使用有权使用的数据自行生成。详见 `THIRD_PARTY_NOTICES.md`。

## 发布前检查

- 确认 `git status` 中没有 `.env`、浏览器配置、日志、截图、Cookie 或密钥；
- 确认 OCS 上游 MIT 声明和第三方通知仍然保留；
- 确认字形指纹资产的再分发授权；
- 运行全部测试和 JavaScript 语法检查；
- 用非计分测试页面验证，并始终保持“只保存、不提交”。

## 免责声明

软件按“原样”提供，不保证答案准确、持续兼容或适合特定用途。使用者对账号风险、课程后果、数据处理和合规性自行负责。本说明不是法律意见。
