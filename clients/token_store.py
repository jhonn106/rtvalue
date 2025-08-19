from auth.stockbit_login import get_bearer_token, load_token_if_valid

def ensure_bearer():
    token = load_token_if_valid()
    if token:
        return token
    return get_bearer_token()
