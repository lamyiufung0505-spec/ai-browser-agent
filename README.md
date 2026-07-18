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
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium   # 首次需下载浏览器
```

在 `.env` 里填入你的 `DEEPSEEK_API_KEY`（复用 ai-hedge-fund 的同一个 key 即可）。

## 使用

```bash
# 中文任务，自动导航
.venv\Scripts\python.exe -m src.cli run "打开 example.com 并告诉我页面标题"

# 指定起点 + 搜索任务
.venv\Scripts\python.exe -m src.cli run "在百度搜索 AAPL 股价并告诉我第一条结果" --url https://www.baidu.com

# 无界面模式（服务器/自动化测试）
.venv\Scripts\python.exe -m src.cli run "..." --headless
```

## 支持的动作

| action | 说明 |
|---|---|
| `click` | 点击元素 `{action:"click","element_id":3}` |
| `type` | 输入文字，可 `submit:true` 输完回车 |
| `scroll` | 滚动 `direction:"down"/"up"` |
| `navigate` | 跳转网址（仅限 http/https） |
| `go_back` | 返回上一页 |
| `done` | 任务完成，返回答案 |

## 安全说明

- 默认最多 15 步（`MAX_STEPS`），防止失控。
- `navigate` 只允许 http/https，禁止访问本地文件（`file://`）。
- 运行在你的本机浏览器，建议先在"只读查阅类"任务上试用。

## 局限

- 纯文本观察，对"看截图/验证码/复杂视觉布局"无能为力（那是多模态 Agent 的方向）。
- 页面结构多变时可能点错；复杂任务可调大 `--max-steps`。
