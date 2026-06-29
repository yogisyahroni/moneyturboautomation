"""
Config bridge — menghubungkan modul baru dengan config MoneyPrinterTurbo
"""
import os
import json

# Default: baca dari MONEYTURBO_CONFIG env var (di-set oleh run.py)
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

app = _get_config()
