"""命令行入口：

    python -m src.cli run "在百度搜索 AAPL 股价并告诉我第一条结果"
"""
import argparse

from .agent import run


def main():
    p = argparse.ArgumentParser(description="浏览器执行 Agent（Playwright + DeepSeek）")
    sub = p.add_subparsers(dest="cmd")

    r = sub.add_parser("run", help="执行一个网页任务")
    r.add_argument("task", help="要完成的任务，如 '打开 example.com 并告诉我页面标题'")
    r.add_argument("--url", default=None, help="起始网址（不填则从空白页开始自行导航）")
    r.add_argument("--max-steps", type=int, default=15, help="最多执行多少步")
    r.add_argument("--headless", action="store_true", help="无界面模式（适合服务器/自动化测试）")

    args = p.parse_args()
    if args.cmd == "run":
        print(run(args.task, start_url=args.url, max_steps=args.max_steps, headless=args.headless))
    else:
        p.print_help()


if __name__ == "__main__":
    main()
