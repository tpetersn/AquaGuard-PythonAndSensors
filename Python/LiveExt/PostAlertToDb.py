import requests
import time

# Auth0 config
AUTH0_URL = "https://dev-1uv6k6fg33hn7eoe.us.auth0.com/oauth/token"
CLIENT_ID = "FJnwHhH8HBqL2nu8rHoyPwtVVRwApRJ5"
CLIENT_SECRET = "bS9JqG-EsdfuU4dVa662CVdXzHjg8NW0sVwMylHKE16TxgJwAO20evCqxaxyXF89"
AUDIENCE = "https://pbrobot.onrender.com/"

# API endpoint (deviceId will be added dynamically)
API_URL = "https://pbrobot.onrender.com/api/alerts"

# Token cache
_token = None
_token_expiry = 0  # unix timestamp when token expires


def _get_token():
    """Fetch a new Auth0 token and cache it with expiry time."""
    global _token, _token_expiry

    headers = {"content-type": "application/json"}
    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "audience": AUDIENCE,
        "grant_type": "client_credentials"
    }

    response = requests.post(AUTH0_URL, json=payload, headers=headers)
    response.raise_for_status()

    data = response.json()
    _token = data["access_token"]
    _token_expiry = time.time() + data.get("expires_in", 3600) - 60  # buffer


def _get_valid_token():
    """Return a valid token, refreshing if expired or missing."""
    global _token, _token_expiry
    if _token is None or time.time() >= _token_expiry:
        _get_token()
    return _token


def send_alert(device_id, alert_type, message, severity):
    """
    Post an alert to the backend.
    """
    token = _get_valid_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    payload = {
        "alertType": alert_type,
        "message": message,
        "severity": severity,
    }

    url = f"{API_URL}/{device_id}"

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


# Interactive test runner
if __name__ == "__main__":
    try:
        print("🔧 Enter alert details:")
        device_id = "68cc90c7ef0763dddf1a5e9d"

        alert_type = input("Alert Type (e.g., 'temperature', 'battery'): ").strip()
        message = input("Message: ").strip()
        severity = input("Severity (info/warning/critical): ").strip()

        result = send_alert(
            device_id,
            alert_type=alert_type,
            message=message,
            severity=severity
        )

        print("✅ Alert posted successfully:", result)

    except requests.exceptions.RequestException as e:
        print("❌ Error:", e)
