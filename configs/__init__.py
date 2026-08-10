"""
全局配置加载模块
从 .env 和 configs/*.yaml 加载配置，供所有模块使用
"""
import os
from pathlib import Path
from dotenv import load_dotenv
import yaml

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent

# 加载 .env
load_dotenv(ROOT_DIR / ".env")


def load_yaml_config(filename: str) -> dict:
    """加载 YAML 配置文件，支持环境变量替换"""
    config_path = ROOT_DIR / "configs" / filename
    with open(config_path, "r", encoding="utf-8") as f:
        raw = f.read()

    # 简单环境变量替换：${VAR:-default}
    import re
    def replace_env(match):
        var_name = match.group(1)
        default = match.group(3) if match.group(3) else ""
        return os.getenv(var_name, default)

    raw = re.sub(r'\$\{([^}:]+)(:-([^}]*))?\}', replace_env, raw)
    return yaml.safe_load(raw)


# 加载所有配置
ES_CONFIG = load_yaml_config("es_config.yaml")
KAFKA_CONFIG = load_yaml_config("kafka_config.yaml")
AGENT_CONFIG = load_yaml_config("agent_config.yaml")

# 常用快捷访问
ES_HOST = os.getenv("ES_HOST", "http://localhost:9200")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
