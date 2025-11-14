import requests
import time

# Auth0 config
AUTH0_URL = "https://dev-1uv6k6fg33hn7eoe.us.auth0.com/oauth/token"
CLIENT_ID = "FJnwHhH8HBqL2nu8rHoyPwtVVRwApRJ5"
CLIENT_SECRET = "bS9JqG-EsdfuU4dVa662CVdXzHjg8NW0sVwMylHKE16TxgJwAO20evCqxaxyXF89"
AUDIENCE = "https://pbrobot.onrender.com/"

# API endpoint
API_URL = "https://pbrobot.onrender.com/api/readings"

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


def post_reading(device_id, temperature=None, ph=None, chlorine=None,
                 tds=None, battery_voltage=None, battery_percentage=None):
    """
    Post a sensor reading to the backend.
    """
    token = _get_valid_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "deviceId": device_id,
        "temperature": temperature,
        "pH": ph,
        "chlorine": chlorine,
        "tds": tds,
        "batteryVoltage": battery_voltage,
        "batteryPercentage": battery_percentage
    }

    # remove None values
    payload = {k: v for k, v in payload.items() if v is not None}

    response = requests.post(API_URL, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


# Interactive test runner
if __name__ == "__main__":
    try:
        print("🔧 Enter test values for a reading:")
        device_id = "68cc90c7ef0763dddf1a5e9d"

        # convert inputs safely
        def safe_float(prompt):
            val = input(prompt).strip()
            return float(val) if val else None

        temperature = safe_float("Temperature (°C): ")
        ph = safe_float("pH: ")
        chlorine = safe_float("Chlorine (ppm): ")
        tds = safe_float("TDS (ppm): ")
        battery_voltage = safe_float("Battery Voltage (V): ")
        battery_percentage = safe_float("Battery Percentage (%): ")

        result = post_reading(
            device_id,
            temperature=temperature,
            ph=ph,
            chlorine=chlorine,
            tds=tds,
            battery_voltage=battery_voltage,
            battery_percentage=battery_percentage
        )
        print("✅ Reading posted successfully:", result)

    except requests.exceptions.RequestException as e:
        print("❌ Error:", e)
