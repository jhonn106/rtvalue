import os
from auth.stockbit_login import get_bearer_token, load_token_if_valid, save_token

def ensure_bearer():
    # ENV wins
    env_tok = os.environ.get("STOCKBIT_BEARER")
    if env_tok and env_tok.strip():
        return env_tok.strip()

    token = load_token_if_valid()
    if token:
        return token
    # mintalah ke auth (akan fallback ke Playwright bila perlu)
    return get_bearer_token()
