"""
Config bridge — menghubungkan modul baru dengan config MoneyPrinterTurbo
Format: Match `from app.config import config` → config.app.get() pattern
"""
import os
import json

_default = {
    "llm_provider": "openai",
    "openai_api_key": "sk-9router",
    "openai_base_url": "http://localhost:20128/v1",
    "openai_model_name": "gratis",
    "pexels_api_keys": ["SLOaFHz0krNOovfSTSUCHHHmc5f1ogtDzjoRPAjIyXfyt5XP8yKpbay2"],
}

def _get_config():
    env_cfg = os.environ.get("MONEYTURBO_CONFIG")
    if env_cfg:
        try:
            return json.loads(env_cfg)
        except json.JSONDecodeError:
            pass
    return dict(_default)

# Struct yang cocok sama interface app.config:
# config.app.get("key") → dict-like access
class ConfigBridge:
    def __init__(self):
        self.app = _get_config()
        self.ui = {}
        self.whisper = {}
        self.proxy = {}
        self.azure = {}
        self.siliconflow = {}
        self.elevenlabs = {}
        self.chatterbox = {}
        self.log_level = "INFO"
        self.listen_host = "0.0.0.0"
        self.listen_port = 8080
        self.project_name = "MoneyTurboAutomation"
        self.project_version = "2.0.0"
        self.project_description = "Automated content creation"

config = ConfigBridge()
