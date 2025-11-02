from pathlib import Path

from dynaconf import Dynaconf

SRC_BASE_DIR = Path(__file__).resolve().parent.parent
CONFIGS_BASE_DIR = SRC_BASE_DIR / "configs"
PROMPTS_BASE_DIR = SRC_BASE_DIR / "prompts"

logger_config = Dynaconf(settings_files=[f"{CONFIGS_BASE_DIR}/logger_config.yaml"])
messages_config = Dynaconf(settings_files=[f"{CONFIGS_BASE_DIR}/messages_config.yaml"])
bot_config = Dynaconf(settings_files=[f"{CONFIGS_BASE_DIR}/bot_config.yaml"])
