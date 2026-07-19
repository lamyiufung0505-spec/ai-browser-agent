# 浏览器执行 Agent（ai-browser-agent）

一个能**自己操作真实浏览器**完成任务的 AI Agent：你用大白话下指令，
它观察页面 → 决定下一步点哪里/输什么 → 执行 → 循环，直到任务完成。

基于 **Playwright**（控制浏览器）+ **DeepSeek**（决策大脑），纯文本模型即可，
**不需要视觉多模态模型**。

## 它和前几个项目的区别

| 项目 | 能力 |
|---|---|
| ai-travel-agent | 调用工具（搜索）给建议 |
| ai-hedge-fund | 多 Agent 并行分析 |
| ai-rag-qa | 检索文档后回答 |
| **ai-browser-agent** | **真正去网页上"做"事情**（点、输、翻、跳转） |

前三个都是"说"，这个是"做"。

## 工作原理（ReAct 循环）

```
你下达任务
   → 浏览器打开页面，抽取"可交互元素列表"（按钮/链接/输入框，各带 id）
   → 把 任务 + 当前URL + 元素列表 + 历史动作 喂给 DeepSeek
   → DeepSeek 返回下一步 JSON 动作（click / type / scroll / navigate / go_back / done）
   → 执行该动作，刷新页面状态
   → 循环，直到 done 或达到最大步数
```

观察方式是给页面元素注入 `data-id` 并过滤不可见项，所以纯文本模型也能"看见"页面。

## 安装

```bash
# 1) 克隆仓库
git clone https://github.com/lamyiufung0505-spec/ai-browser-agent.git
cd ai-browser-agent

# 2) 创建虚拟环境并装依赖（ Windows 用 .venv\Scripts\python.exe，Mac/Linux 用 .venv/bin/python ）
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium   # 首次需下载浏览器内核

# 3) 配置密钥：把仓库里的 .env.example 复制成 .env，填入你的 Key
copy .env.example .env          # Windows
# cp .env.example .env          # Mac / Linux
```

在 `.env` 里填入 `DEEPSEEK_API_KEY`（申请：https://platform.deepseek.com/）。
普通任务只填这一个即可；只有需要"识别图片验证码"时才填 VISION_* 三项（详见 .env.example 注释）。

## 使用

```bash
# 中文任务，自动导航
.venv\Scripts\python.exe -m src.cli run "打开 example.com 并告诉我页面标题"

# 指定起点 + 搜索任务
.venv\Scripts\python.exe -m src.cli run "在百度搜索 AAPL 股价并告诉我第一条结果" --url https://www.baidu.com

# 无界面模式（服务器/自动化测试）
.venv\Scripts\python.exe -m src.cli run "..." --headless
```

## 网页界面

项目也提供了 Gradio 网页界面，输入任务和参数后，Agent 会自动执行，并在页面右侧实时展示每一步的过程日志：

```bash
.venv\Scripts\python.exe -m src.web
```

启动后浏览器打开 `http://localhost:7860` 即可使用。

## 支持的动作

| action | 说明 |
|---|---|
| `click` | 点击元素 `{action:"click","element_id":3}` |
| `type` | 输入文字，可 `submit:true` 输完回车 |
| `scroll` | 滚动 `direction:"down"/"up"` |
| `navigate` | 跳转网址（仅限 http/https） |
| `go_back` | 返回上一页 |
| `done` | 任务完成，返回答案 |
| `solve_captcha` | 遇到图片形式验证码时，截图交给视觉模型识别后回填（需配置 VISION_*） |

## 安全说明

- 默认最多 15 步（`MAX_STEPS`），防止失控。
- `navigate` 只允许 http/https，禁止访问本地文件（`file://`）。
- 运行在你的本机浏览器，建议先在"只读查阅类"任务上试用。

## 最小可运行示例

装好依赖、填好 `.env` 后，先用一个"只读查阅类"任务验证链路是否通：

```bash
.venv\Scripts\python.exe -m src.cli run "打开 https://example.com，告诉我页面主标题是什么"
```

能正常返回标题，说明安装成功。

## 局限

- 默认纯文本观察，不依赖视觉模型即可跑大多数任务；遇到**图片形式验证码**时，可配置可选的视觉模型（见 `.env.example`）来识别。
- 页面结构多变时可能点错；复杂任务可调大 `--max-steps`。
- 不擅长需要登录态、滑块验证、或强反爬（如淘宝）的任务——这类建议先准备好登录态再跑。
