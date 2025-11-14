LiveFeed.py — Raspberry Pi Camera Publisher

This script streams video from a Raspberry Pi (or any webcam) to a LiveKit Cloud
 room.

Install dependencies

Run these in your Python environment:

pip install opencv-python
pip install requests
pip install livekit

If you don’t need GUI support (e.g. headless Pi), use:

pip install opencv-python-headless

Usage

Edit LiveFeed.py and update:

ROOM_URL = "wss://pbrobot-ir91vwzj.livekit.cloud"
TOKEN_URL = "https://pbrobot.onrender.com/getToken?identity=raspberry&roomName=pool"


Run:

python LiveFeed.py


You should see logs like:

Got token: eyJhbGciOiJIUzI1NiJ9.eyJ2aWRlbyI6eyJyb29 ...
✅ Track publish request done: TR_V5Ce9RLM5MEnv
👤 Participant joined: viewer (When the frontend is opened from https://pool-bot.netlify.app/)