from dynaconf import Dynaconf

BASE_DIR = "src/configs"

logger_config = Dynaconf(settings_files=[f"{BASE_DIR}/logger_config.yaml"])
messages_config = Dynaconf(settings_files=[f"{BASE_DIR}/messages_config.yaml"])
bot_config = Dynaconf(settings_files=[f"{BASE_DIR}/bot_config.yaml"])
