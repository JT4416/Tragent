import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_ROOT = Path(__file__).parent.parent
_config_path = _ROOT / "config" / "config.yaml"

with open(_config_path) as f:
    _cfg = yaml.safe_load(f)


def get(section: str, key: str):
    return _cfg[section][key]


def api_key(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise EnvironmentError(f"Missing required env var: {name}")
    return value


ANTHROPIC_API_KEY = lambda: api_key("ANTHROPIC_API_KEY")
SCHWAB_APP_KEY = lambda: api_key("SCHWAB_APP_KEY")
SCHWAB_APP_SECRET = lambda: api_key("SCHWAB_APP_SECRET")
SCHWAB_CALLBACK_URL = lambda: api_key("SCHWAB_CALLBACK_URL")
ALPHA_VANTAGE_API_KEY = lambda: api_key("ALPHA_VANTAGE_API_KEY")
NEWS_API_KEY = lambda: api_key("NEWS_API_KEY")
QUIVER_QUANT_API_KEY = lambda: api_key("QUIVER_QUANT_API_KEY")
