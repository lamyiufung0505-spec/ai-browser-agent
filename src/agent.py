"""ReAct 浏览器智能体：观察页面 → 让 DeepSeek 决定下一步动作 → 执行 → 循环。

整个循环只靠文本：把页面可交互元素列表喂给 DeepSeek（纯文本模型），
它返回 JSON 动作，我们照做。不需要视觉多模态模型，免费可用。
"""
import json
from openai import OpenAI

from .config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    VISION_API_KEY,
    VISION_BASE_URL,
    VISION_MODEL,
    MAX_STEPS,
)
from .browser import BrowserSession

SYSTEM_PROMPT = """你是一个控制真实浏览器的 AI 智能体。你会收到：
- 用户的任务目标
- 当前页面的 URL / 标题
- 页面上可交互元素列表（每个有 id、类型、可见文字）
- 页面文字（参考）：当前页可见的正文文字（如天气、说明、结果摘要等），可直接引用其内容来回答，无需点击
- 你之前执行过的动作历史

你的工作是决定【下一步】该做什么，只输出一个 JSON 对象，不要输出任何解释或多余文字。

可执行的动作（action 字段必须取其一）：
- {"action":"click","element_id":<数字>}           点击某个元素
- {"action":"type","element_id":<数字>,"text":"<要输入的内容>","submit":<true或false>}   在输入框输入；submit 为 true 时输完按回车
  （type 动作请作用在 tag 为 input/textarea 或可输入的元素上，其 type 字段通常为 text/search/email 等；不要作用在普通按钮或链接上）
- {"action":"scroll","direction":"down"或"up"}      滚动页面
- {"action":"navigate","url":"<完整网址，必须以 http 开头>"}   跳转到某个网址
- {"action":"go_back"}                           返回上一页
- {"action":"done","answer":"<用中文给出任务最终答案或你找到的信息>"}   任务完成
- {"action":"solve_captcha","image_id":<数字>,"input_id":<数字>}  识别图片验证码：对 image_id 所指的验证码图片截图，用视觉模型识别其中的数学表达式并算出答案，自动填入 input_id 对应的输入框（不提交）。仅当遇到【图片形式】的计算验证码（题目是一张图、文字里读不到）时才用。

规则：
1. 每次只输出一个动作。
2. 当任务已经完成、或你已收集到足够信息时，输出 done 并给出答案。
3. 不要重复做和上一步完全一样的无效动作；如果卡住，尝试 scroll 或 navigate。
4. 只使用列表里提供的 element_id，不要编造。
5. 只允许通过 navigate 访问 http/https 网址。
6. 【最重要】done 里的 answer 必须严格来自你在【当前页面】实际看到的内容，包括：
   - 【可交互元素】列表里的文字，以及
   - 【页面文字（参考）】里的正文（如天气、温度、数字、说明等）。
   二者都算"真实看到"，可一字不差地引用；绝对不能凭想象编造任何标题、内容或数字。
7. 如果当前列表里找不到任务需要的信息，不要急着 done：先尝试 scroll 向下滚动、
   或点进相关链接查看；确实找不到时，done 的 answer 要如实说明"未能在页面上找到"，
   而不是编一个看起来合理的答案。
8. 搜索类任务：提交搜索词后，搜索结果通常就直接出现在【可交互元素】列表里
   （表现为一串带标题文字的 <a> 链接）。请直接从列表里读取结果标题作答，
   一般不需要再点击就能回答"第一个结果的标题是什么"这类问题。
9. 如果【页面文字（参考）】里已经包含任务相关的具体数据（例如温度、天气状况、℃、具体数字、
   说明文字），优先直接据此调用 done 综合给出答案，【不要点进外部链接去寻找】——一旦跳走，
   当前页这些现成数据就丢了。只有当页面文字里完全没有任务相关信息时，才按规则 10 点进链接。
10. 信息类任务（查天气、股价、资料等）如果在当前页没直接看到答案，但搜索结果里有相关链接
   （天气网站、百科、官网、新闻等），应先点进【最相关】的那条链接，在新页面读取信息后再 done；
   不要直接报告"找不到"。只有当点进相关链接后仍然读不到，才如实说明"未能找到"。
11. 如果遇到【图片形式】的验证码（题目是一张图，页面文字里读不到算式），不要用 click/type 瞎试，
   改用 solve_captcha 动作：image_id 填【验证码图片】的 data-id，input_id 填【要填答案的输入框】的 data-id。
12. 查询天气、股价、资料等信息时，优先直接从【当前搜索结果页的页面文字（参考）】里读取答案
   （搜索结果摘要里常已含天气/温度/股价等关键信息）。若需要更详细的数据，优先【点击搜索
   结果里的链接】（点击会带上来源信息，通常能正常打开）；而【不要直接 navigate 到天气网站/
   官网】——这类站点常屏蔽自动化浏览器、返回 403 拦截页，会让你在空页面间反复刷新却读不到数据。
13. 【多实体任务】如果任务要求查询【多个对象】（例如“北京和上海”“A 与 B”“三款手机”），
    必须按顺序执行：先获取第一个对象的完整数据，再获取第二个对象的完整数据，依此类推。
    在【所有对象的数据都拿到并按要求对比/汇总完成】之前，绝对不能调用 done。
    禁止在搜索结果页之间来回切换 query 却不读取任何数据，这种行为会让步数浪费在无效跳转上。
    每次输出动作前，请确认：当前正在解决哪个对象？它的数据已拿到了吗？
    没拿到就该点进结果或读取摘要；拿到了才切换下一个对象。
    特别注意：当通过 navigate 进入某个对象的信息页面后，必须先 scroll 或直接读取该页面文字，
    把该对象的完整数据拿到手，再 navigate 去下一个对象。禁止连续 navigate 多个对象页面
    却不在任何一个页面停留读取。
14. 搜索结果页里的链接/摘要常常已经包含天气、温度、股价等答案。信息类任务应优先
    从搜索结果摘要里直接提取答案，而不是反复切换 query 或逐个点进外部链接。只有在
    摘要确实缺少关键信息时，才点进最相关的一条链接。"""


def _build_user_prompt(task: str, state: dict, history: list, stuck_hint: str = "") -> str:
    elems = state.get("elements", [])[:50]
    if elems:
        lines = [
            f"  [{e['id']}] <{e['tag']}> {e.get('text') or e.get('placeholder') or e.get('type')}"
            for e in elems
        ]
        elem_block = "\n".join(lines)
    else:
        elem_block = "  (本页目前没有可交互元素，可尝试 scroll 或 navigate）"

    texts = state.get("texts", [])[:50]
    if texts:
        text_block = "\n".join(f"  · {t}" for t in texts)
    else:
        text_block = "  (本页暂无额外正文文字）"

    hist_block = "\n".join(history) if history else "  (无）"

    hint_block = ("\n" + stuck_hint + "\n") if stuck_hint else ""

    return f"""【任务】{task}

【当前页面】
URL: {state.get('url')}
标题: {state.get('title')}

【可交互元素】
{elem_block}

【页面文字（参考，可直接引用作答，无需点击）】
{text_block}

【你已执行的动作】
{hist_block}
{hint_block}
请输出下一步动作（只输出 JSON）："""


def _parse_action(text: str) -> dict | None:
    s = (text or "").strip()
    if "```" in s:
        s = s.split("```")[1]
        if s.startswith("json"):
            s = s[4:]
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(s[start : end + 1])
    except Exception:
        return None


def _sig(state: dict) -> int:
    """页面状态签名：用于判断"某次操作后页面是否发生变化"。"""
    url = state.get("url", "")
    elems = state.get("elements", [])
    epart = "|".join(f"{e.get('id')}:{e.get('text')}" for e in elems)
    tpart = "|".join(state.get("texts", [])[:50])
    return hash((url, epart, tpart))


def _ask_vision(client, image_path: str) -> str:
    """把验证码图片发给视觉模型，返回识别出的数字答案。"""
    import base64

    if client is None:
        raise RuntimeError("未配置 VISION_API_KEY，无法识别图片验证码（DeepSeek 不支持看图）")
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    resp = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "这是一道数学验证码图片。请识别其中的数学表达式并计算，只返回最终的数字答案，不要任何解释或标点。",
                    },
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }
        ],
        max_tokens=20,
    )
    return resp.choices[0].message.content.strip()


def run(task: str, start_url: str = None, max_steps: int = MAX_STEPS, headless: bool = False, on_step=None) -> str:
    if not DEEPSEEK_API_KEY:
        return "❌ 未设置 DEEPSEEK_API_KEY，请在 .env 里填入你的 DeepSeek key。"

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    vclient = OpenAI(api_key=VISION_API_KEY, base_url=VISION_BASE_URL) if VISION_API_KEY else None
    browser = BrowserSession(headless=headless)
    history = []
    result = "（未返回结果）"

    try:
        if start_url:
            print(f"🌐 打开起始页：{start_url}")
            try:
                browser.navigate(start_url)
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️ 起始页打不开（网址可能无效或无网络）：{str(e).splitlines()[0][:120]}")
                return f"【任务】{task}\n\n❌ 起始页 {start_url} 无法打开，请检查网址是否正确、网络是否可用。"
        else:
            print("🌐 从空白页开始，由模型自行导航")

        prev_sig = None          # 上一步“执行前”的页面签名
        repeat_count = {}        # 统计 (动作,元素) 连续无变化的次数
        recent_sigs = []        # 最近若干步的页面签名，用于检测“来回横跳”振荡
        last_act = None
        last_elem = None
        for step in range(1, max_steps + 1):
            state = browser.get_state()

            # —— 卡死 / 振荡 / 拦截 检测 ——
            stuck_hint = ""
            cur_sig = _sig(state)
            cur_texts = " ".join(state.get("texts", []) or [])

            # (a) 拦截页检测：网站返回 403 / Forbidden 等反爬拦截，根本读不到数据
            if ("403" in cur_texts and "Forbid" in cur_texts) or "Forbid_code" in cur_texts:
                history.append("⚠️ 当前页面被网站拦截（403 Forbidden），这里读不到任何任务数据。")
                if on_step:
                    on_step(step, history[-1])
                stuck_hint = (
                    "【紧急提醒】你正停留在一个被拦截的页面（403），无论怎么刷新/重导航都读不到数据。"
                    "立即 go_back 返回搜索页，改用【页面文字（参考）】里的搜索摘要作答；"
                    "或者重新在 Bing 搜索、并【点击结果里的链接】（点击会带来来源信息、通常能正常打开），"
                    "绝对不要再 navigate 到这个被拦的网站。"
                )

            # (b) 同一元素连续无效操作（原卡死检测）
            elif prev_sig is not None and cur_sig == prev_sig:
                history.append(
                    f"⚠️ 上一步（{last_act} #{last_elem}）执行后页面无任何变化，请勿重复无效操作。"
                )
                if on_step:
                    on_step(step, history[-1])
                key = (last_act, last_elem)
                repeat_count[key] = repeat_count.get(key, 0) + 1
                if repeat_count[key] >= 2:
                    stuck_hint = (
                        "【紧急提醒】你已连续多次对【同一元素】执行相同操作，但页面毫无变化。"
                        "请立即停止该重复操作：如果页面上（含“页面文字（参考）”）已有任务所需信息，"
                        "立刻用 done 回答；否则改用 scroll 向下滚动、navigate 换网址、或点击【其他】元素，"
                        "绝对不要再点击刚才那个元素。"
                    )

            # (c) 振荡检测：最近几步在 2 个以内页面之间反复横跳（A→B→A→B）
            recent_sigs.append(cur_sig)
            if len(recent_sigs) > 8:
                recent_sigs.pop(0)
            if not stuck_hint and len(recent_sigs) >= 4 and len(set(recent_sigs[-6:])) <= 2:
                stuck_hint = (
                    "【紧急提醒】检测到你在少数几个页面之间反复横跳（导航来导航去却始终读不到新信息），"
                    "这已经是死循环。立即停止 navigate/click 循环：如果当前页【页面文字（参考）】里"
                    "已有部分答案就直接 done 作答（可说明部分信息未能获取）；否则换一种根本不同的做法"
                    "（例如重新搜索、或只读搜索结果里的摘要），不要再回到刚去过的那几个网址。"
                )

            user = _build_user_prompt(task, state, history, stuck_hint)

            try:
                resp = client.chat.completions.create(
                    model=DEEPSEEK_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user},
                    ],
                    temperature=0.1,
                )
                raw = resp.choices[0].message.content
            except Exception as e:  # noqa: BLE001
                print(f"  ⚠️ 调用 DeepSeek 失败：{e}")
                break

            action = _parse_action(raw)
            if not action:
                print(f"  ⚠️ 第 {step} 步：模型未返回合法 JSON，跳过。原始：{raw[:120]}")
                history.append(f"[step {step}] (解析失败）")
                if on_step:
                    on_step(step, history[-1])
                continue

            act = action.get("action")
            print(f"  ▶ 第 {step} 步：{action}")

            if act == "done":
                done_ans = action.get("answer", result)
                # —— 半成品拦截：若答案里自己承认还缺数据/没对比，判定为中途放弃，拒收并强令继续 ——
                _giveup = [
                    "需要先", "建议先", "先查询", "先获取", "先查", "先去",
                    "无法直接对比", "无法对比", "还不能对比",
                    "当前页面没有", "页面没有", "没有拿到", "尚未获取", "还未获取",
                    "还没拿到", "缺失", "缺数据", "缺少数据", "无法获得",
                ]
                if any(k in done_ans for k in _giveup) and step < max_steps:
                    print(f"  ⛔ 第 {step} 步：检测到 done 答案存在半成品（自述仍缺数据），拒收，强制继续。")
                    history.append(
                        f"[step {step}] ⛔ done 被拒：你的答案里承认仍有数据缺失（如“需要先查/没有…数据/无法对比”），"
                        f"任务尚未完成。请继续获取缺失对象的数据：回到搜索页再搜下一个城市/对象，"
                        f"或直接 navigate 到对应页面，拿齐全部数据并按要求对比后再 done。绝对不要再次提交这种半成品。"
                    )
                    if on_step:
                        on_step(step, history[-1])
                    continue
                result = done_ans
                history.append(f"[step {step}] done -> {result[:80]}")
                if on_step:
                    on_step(step, history[-1])
                print(f"  ✅ 任务完成")
                break

            # 记录“即将执行”的动作，供下一步判断是否无效
            last_act = act
            last_elem = action.get("element_id")
            skip_sig = False

            # 其余动作统一包在 try/except 里：失败当作"观察"反馈给模型，
            # 让它自行纠错（标准 ReAct 行为），而不是让整个循环崩溃。
            try:
                if act == "click":
                    browser.click(action["element_id"])
                    history.append(f"[step {step}] click #{action['element_id']}")
                    if on_step:
                        on_step(step, history[-1])
                elif act == "type":
                    browser.type(
                        action["element_id"],
                        action.get("text", ""),
                        submit=bool(action.get("submit", False)),
                    )
                    history.append(f"[step {step}] type #{action['element_id']}: {action.get('text','')[:40]}")
                    if on_step:
                        on_step(step, history[-1])
                elif act == "scroll":
                    browser.scroll(action.get("direction", "down"))
                    history.append(f"[step {step}] scroll {action.get('direction','down')}")
                    if on_step:
                        on_step(step, history[-1])
                elif act == "navigate":
                    url = action.get("url", "")
                    if url.startswith("http"):
                        browser.navigate(url)
                        history.append(f"[step {step}] navigate -> {url}")
                        if on_step:
                            on_step(step, history[-1])
                    else:
                        print(f"  ⚠️ navigate 被拒绝（非 http 网址）：{url}")
                        history.append(f"[step {step}] (navigate 拒绝：{url})")
                        if on_step:
                            on_step(step, history[-1])
                elif act == "go_back":
                    browser.go_back()
                    history.append(f"[step {step}] go_back")
                    if on_step:
                        on_step(step, history[-1])
                elif act == "solve_captcha":
                    img = action.get("image_id")
                    inp = action.get("input_id")
                    if img is None or inp is None:
                        print(f"  ⚠️ solve_captcha 缺少 image_id 或 input_id")
                        history.append(f"[step {step}] (solve_captcha 参数缺失)")
                        if on_step:
                            on_step(step, history[-1])
                    else:
                        try:
                            path = browser.screenshot_element(img)
                            ans = _ask_vision(vclient, path)
                            browser.type(inp, ans, submit=False)
                            history.append(f"[step {step}] solve_captcha 识别答案={ans} 已填入 #{inp}")
                            if on_step:
                                on_step(step, history[-1])
                            skip_sig = True  # 填验证码不改变元素签名，跳过一次无变化检测避免误报
                        except Exception as ve:  # noqa: BLE001
                            vmsg = str(ve).split("\n")[0][:120]
                            print(f"  ⚠️ 第 {step} 步 solve_captcha 失败：{vmsg}")
                            history.append(f"[step {step}] solve_captcha 失败：{vmsg}")
                            if on_step:
                                on_step(step, history[-1])
                else:
                    print(f"  ⚠️ 未知动作：{act}")
                    history.append(f"[step {step}] (未知动作 {act})")
                    if on_step:
                        on_step(step, history[-1])
            except Exception as e:  # noqa: BLE001
                msg = str(e).split("\n")[0][:120]
                print(f"  ⚠️ 第 {step} 步执行失败：{msg}")
                history.append(f"[step {step}] {act} #{action.get('element_id','?')} 执行失败：{msg}")
                if on_step:
                    on_step(step, history[-1])

            # 以“执行前”的页面状态作为下一步比较基线
            # （solve_captcha 只填输入框、不改变元素签名，跳过一次无变化检测避免误报）
            prev_sig = None if skip_sig else _sig(state)
        else:
            print(f"  ⏱️ 已达到最大步数 {max_steps}，停止。")
    finally:
        browser.close()

    return f"【任务】{task}\n\n{result}"
