from dynaconf import Dynaconf

BASE_DIR = "src/configs"

messages_config = Dynaconf(settings_files=[f"{BASE_DIR}/messages_config.yaml"])
