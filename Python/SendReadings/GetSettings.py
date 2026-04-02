import requests
import time

# -----------------------------------------------------------
# Auth0 Configuration
# -----------------------------------------------------------
AUTH0_URL = "https://dev-1uv6k6fg33hn7eoe.us.auth0.com/oauth/token"
CLIENT_ID = "FJnwHhH8HBqL2nu8rHoyPwtVVRwApRJ5"
CLIENT_SECRET = "bS9JqG-EsdfuU4dVa662CVdXzHjg8NW0sVwMylHKE16TxgJwAO20evCqxaxyXF89"
AUDIENCE = "https://pbrobot.onrender.com/"

# -----------------------------------------------------------
# API Endpoint — This fetches User Settings
# -----------------------------------------------------------
SETTINGS_URL = "https://pbrobot.onrender.com/api/settings"

# -----------------------------------------------------------
# Token Cache
# -----------------------------------------------------------
_token = None
_token_expiry = 0     # unix timestamp when token expires


def _get_token():
    """Fetch and cache a fresh Auth0 token."""
    global _token, _token_expiry

    headers = {"content-type": "application/json"}
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "audience": AUDIENCE,
        "grant_type": "client_credentials",
    }

    response = requests.post(AUTH0_URL, json=payload, headers=headers)
    response.raise_for_status()

    data = response.json()
    _token = data["access_token"]
    _token_expiry = time.time() + data.get("expires_in", 3600) - 60  # buffer


def _get_valid_token():
    """Return a cached valid token, refreshing if expired."""
    global _token, _token_expiry

    if _token is None or time.time() >= _token_expiry:
        _get_token()

    return _token


# -----------------------------------------------------------
# Fetch User Settings
# -----------------------------------------------------------
def fetch_user_settings():
    """Fetch the authenticated user's settings document."""
    token = _get_valid_token()
    headers = {"Authorization": f"Bearer {token}"}

    res = requests.get(SETTINGS_URL, headers=headers)
    res.raise_for_status()
    return res.json()


# -----------------------------------------------------------
# Standalone CLI test
# -----------------------------------------------------------
if __name__ == "__main__":
    print("📡 Fetching user settings...")
    try:
        settings = fetch_user_settings()
        print("✅ User settings received:")
        print(settings)

    except requests.exceptions.RequestException as e:
        print("❌ Error fetching settings:", e)
