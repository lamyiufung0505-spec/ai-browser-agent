"""全局配置：密钥、模型、默认行为。改配置优先改 .env，不必动代码。"""
from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# 视觉模型：用于识别“图片形式”的验证码（DeepSeek 本身不支持看图，需另行配置）。
# 任何 OpenAI 兼容的视觉接口都行，例如：
#   - OpenAI：VISION_BASE_URL=https://api.openai.com/v1  VISION_MODEL=gpt-4o-mini
#   - 本地免费：Ollama 跑 llama3.2-vision，VISION_BASE_URL=http://localhost:11434/v1  VISION_API_KEY=ollama  VISION_MODEL=llama3.2-vision
VISION_API_KEY = os.getenv("VISION_API_KEY", "")
VISION_BASE_URL = os.getenv("VISION_BASE_URL", "https://api.openai.com/v1")
VISION_MODEL = os.getenv("VISION_MODEL", "gpt-4o-mini")

MAX_STEPS = int(os.getenv("MAX_STEPS", "15"))
HEADLESS = os.getenv("HEADLESS", "false").lower() in ("1", "true", "yes")
