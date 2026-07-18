"""Playwright 浏览器封装：启动、取页面状态、按 id 执行动作。

观察方式：把页面上可交互元素注入 data-id，过滤掉不可见的，
返回 [{id, tag, type, text, placeholder}] 列表——这样 DeepSeek（纯文本模型）
也能"看见"页面并指定要操作哪个元素，无需视觉多模态模型。
"""
import os
import tempfile
from playwright.sync_api import sync_playwright

# 给所有候选元素按顺序打 data-id 标记（只打一次）
INJECT_JS = r"""
() => {
  const sel = 'a,button,input,select,textarea,[role="button"],[role="link"]';
  document.querySelectorAll(sel).forEach((e, i) => {
    if (!e.hasAttribute('data-id')) e.setAttribute('data-id', String(i));
  });
}
"""

# 采集可见的候选元素信息
COLLECT_JS = r"""
() => {
  const sel = 'a,button,input,select,textarea,[role="button"],[role="link"]';
  const els = [...document.querySelectorAll(sel)].filter(e => {
    const r = e.getBoundingClientRect();
    const vis = r.width > 0 && r.height > 0;
    const st = getComputedStyle(e);
    return vis && st.visibility !== 'hidden' && st.display !== 'none';
  });
  return els.map(e => {
    const raw = (e.innerText || e.value || e.getAttribute('aria-label') || e.placeholder || '').trim().replace(/\s+/g, ' ').slice(0, 80);
    return {
      id: e.getAttribute('data-id'),
      tag: e.tagName.toLowerCase(),
      type: e.type || '',
      text: raw,
      placeholder: e.placeholder || ''
    };
  }).filter(x => x.id !== null);
}
"""


# 采集页面可见的正文文字（按钮/链接以外的纯文本，如天气、说明、结果摘要）。
# 这些文字不是可点击元素，仅供模型阅读作答参考。
TEXT_COLLECT_JS = r"""
() => {
  const sel = 'h1,h2,h3,h4,h5,h6,p,li,td,th,span,div,label,article,section,dd,dt';
  const seen = new Set();
  const out = [];
  for (const e of document.querySelectorAll(sel)) {
    const r = e.getBoundingClientRect();
    const st = getComputedStyle(e);
    if (r.width <= 0 || r.height <= 0 || st.visibility === 'hidden' || st.display === 'none') continue;
    const t = (e.innerText || '').trim().replace(/\s+/g, ' ');
    if (t.length < 2 || t.length > 200) continue;
    if (seen.has(t)) continue;
    seen.add(t);
    out.push(t.slice(0, 120));
    if (out.length >= 50) break;
  }
  return out;
}
"""

class BrowserSession:
    def __init__(self, headless=False):
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(headless=headless)
        # 用接近真实桌面 Chrome 的 UA / 视口 / 语言头，降低被天气/官网等站点
        # 反爬识别为自动化浏览器而返回 403 的概率（非 100% 有效，但无害）。
        self.context = self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
        )
        self.page = self.context.new_page()

    def _settle(self, quiet_ms=1500):
        """等页面基本安定：优先等网络空闲，兜底固定等待。
        用于导航/提交/点击后，确保动态内容（如搜索结果）加载出来再取状态。"""
        try:
            self.page.wait_for_load_state("networkidle", timeout=quiet_ms + 4000)
        except Exception:
            self.page.wait_for_timeout(quiet_ms)

    def navigate(self, url):
        if not url.startswith("http"):
            url = "https://" + url
        self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        self._settle()

    def get_state(self):
        """返回 {url, title, elements:[...], texts:[...]}。
        elements 是可交互元素（可点击/输入）；texts 是页面可见正文文字（供阅读参考）。"""
        try:
            self.page.evaluate(INJECT_JS)
            elements = self.page.evaluate(COLLECT_JS)
            texts = self.page.evaluate(TEXT_COLLECT_JS)
        except Exception:
            elements = []
            texts = []
        # 防御：页面已加载（URL 非空）但采到空，通常是 Bing 等客户端重定向的
        # 时序竞争导致注入/采集跑在过渡态。稍等再采一次。
        if not elements and self.page.url not in ("about:blank", "", None):
            try:
                self.page.wait_for_timeout(800)
                self.page.evaluate(INJECT_JS)
                elements = self.page.evaluate(COLLECT_JS)
                texts = self.page.evaluate(TEXT_COLLECT_JS)
            except Exception:
                pass
        return {
            "url": self.page.url,
            "title": self.page.title(),
            "elements": elements or [],
            "texts": texts or [],
        }

    def click(self, bid):
        before = len(self.page.context.pages)
        self.page.click(f'[data-id="{bid}"]', timeout=8000)
        # Bing 等网站的结果链接常在新标签页打开；若点击后多出标签页，切到最新的那个，
        # 否则智能体会一直停留在原页面、读不到新开页面里的答案。
        pages = self.page.context.pages
        if len(pages) > before:
            for p in reversed(pages):
                if p.url and p.url != "about:blank":
                    self.page = p
                    break
        self._settle()

    def type(self, bid, text, submit=False):
        sel = f'[data-id="{bid}"]'
        try:
            # 优先用 fill：仅对 <input>/<textarea> 有效
            self.page.fill(sel, text, timeout=5000)
        except Exception:
            # 退化方案：先点击获得焦点，再用键盘逐字输入
            # 兼容 contenteditable 容器 / 包裹层等非原生输入框
            try:
                self.page.click(sel, timeout=5000)
            except Exception:
                pass
            self.page.keyboard.type(text, delay=20)
        self.page.wait_for_timeout(300)
        if submit:
            try:
                self.page.press(sel, "Enter")
            except Exception:
                self.page.keyboard.press("Enter")
            # 提交后等结果页真正加载出来（搜索结果是动态渲染的）
            self._settle()

    def screenshot_element(self, bid, path=None):
        """对指定 data-id 的元素截图，返回图片路径（默认存系统临时目录）。"""
        if path is None:
            path = os.path.join(tempfile.gettempdir(), f"captcha_{bid}.png")
        el = self.page.query_selector(f'[data-id="{bid}"]')
        if el is None:
            raise RuntimeError(f"找不到元素 #{bid}，无法截图")
        el.screenshot(path=path)
        return path

    def scroll(self, direction="down"):
        dy = 600 if direction == "down" else -600
        self.page.mouse.wheel(0, dy)
        self.page.wait_for_timeout(400)

    def go_back(self):
        self.page.go_back()
        self.page.wait_for_timeout(600)

    def close(self):
        try:
            self.browser.close()
        finally:
            self.pw.stop()
