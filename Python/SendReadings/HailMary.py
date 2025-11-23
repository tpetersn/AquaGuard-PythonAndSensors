import asyncio
import aiohttp
from livekit import rtc

# --- LiveKit Config ---
ROOM_URL = "wss://pbrobot-ir91vwzj.livekit.cloud"
TOKEN_URL = "https://pbrobot.onrender.com/getToken?identity=raspberry&roomName=pool"

# --- Camera Config ---
DEVICE = "/dev/video0"
WIDTH = 1280
HEIGHT = 720
FPS = 30


async def fetch_token():
    """Fetches a JWT token from your token server."""
    async with aiohttp.ClientSession() as session:
        async with session.get(TOKEN_URL) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Failed to fetch token: {resp.status} {text}")
            return await resp.text()


async def main():
    print("📡 Fetching token...")
    token = await fetch_token()
    print("✅ Token received")

    # Create room
    room = rtc.Room()

    print("🔗 Connecting to LiveKit...")
    await room.connect(ROOM_URL, token)
    print("✅ Connected as:", room.local_participant.identity)

    print("🎥 Initializing V4L2 camera:", DEVICE)
    video_track = rtc.LocalVideoTrack.create_v4l2_device(
        device=DEVICE,
        width=WIDTH,
        height=HEIGHT,
        fps=FPS
    )

    print("📤 Publishing video stream...")
    await room.local_participant.publish_track(
        video_track,
        rtc.TrackPublishOptions(name="raspi-camera")
    )

    print("🚀 Camera is now LIVE in the room!")
    print("Press CTRL+C to stop.")

    # Keep running forever
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user.")
