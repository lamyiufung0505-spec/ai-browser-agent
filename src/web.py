import gradio as gr
from .agent import run


def run_task(task, start_url, max_steps, headless):
    logs = []

    def on_step(step, msg):
        logs.append(f"[{step}] {msg}")

    answer = run(
        task=task,
        start_url=start_url or "https://bing.com",
        max_steps=int(max_steps),
        headless=bool(headless),
        on_step=on_step,
    )
    return answer, "\n".join(logs)


with gr.Blocks(title="浏览器 Agent") as demo:
    gr.Markdown("# 浏览器执行 Agent")
    with gr.Row():
        with gr.Column():
            task = gr.Textbox(label="任务", placeholder="查今天北京天气")
            start_url = gr.Textbox(label="起点网址", value="https://bing.com")
            max_steps = gr.Number(value=15, label="最大步数")
            headless = gr.Checkbox(value=True, label="无头模式")
            btn = gr.Button("运行", variant="primary")
        with gr.Column():
            answer = gr.Textbox(label="结果", lines=8)
            log = gr.Textbox(label="执行过程", lines=12)
    btn.click(run_task, [task, start_url, max_steps, headless], [answer, log])

if __name__ == "__main__":
    demo.launch()
