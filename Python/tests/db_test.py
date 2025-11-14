import json
import requests
from SendReadings import post_reading

AUTH0_DOMAIN = "dev-1uv6k6fg33hn7eoe.us.auth0.com"
CLIENT_ID = "fzjktDzgKdS4B8L2trOu5kXy3nBsFeDj"
AUDIENCE = "https://pbrobot.onrender.com/"
USERNAME = "testuser@test.test"
PASSWORD = "Test1234!"

def test_database_write():
    device_id = "68cc90c7ef0763dddf1a5e9d"
    data_sent = {
        "temperature": 23.5,
        "ph": 7.4,
        "tds": 400,
        "battery_voltage": 3.8,
        "battery_percentage": 85
    }

    # send data
    sent_response = post_reading(device_id, **data_sent)
    assert sent_response["device"] == device_id

    print("Response from the backend:")
    print(sent_response)
    print("✅ Database send test passed.")
    

def get_user_token():
    url = f"https://{AUTH0_DOMAIN}/oauth/token"
    payload = {
        "grant_type": "password",
        "username": USERNAME,
        "password": PASSWORD,
        "audience": AUDIENCE,
        "client_id": CLIENT_ID,
        # optional if you have a client secret for a confidential app:
        "client_secret": "_4xk0AhGZ5cfeVrZUJiUK6Oibz1wY_eGTV2SX8hIY75sd9KyhPc5iewgAiHxMe1O"
    }
    headers = {"content-type": "application/json"}
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()["access_token"]

def get_device_readings(device_id):
    token = get_user_token()
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"https://pbrobot.onrender.com/api/readings/device/{device_id}", headers=headers)
    r.raise_for_status()
    print("✅ Authenticated as user, got readings:")
    print(r.json())

    

if __name__ == "__main__":
    test_database_write()
    get_device_readings("68cc90c7ef0763dddf1a5e9d")
