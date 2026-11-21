import os
from mcp.server.fastmcp import FastMCP

# Render injects the PORT environment variable (usually 10000)
PORT = int(os.getenv("PORT", 8000))

# Must listen on 0.0.0.0 so Render can forward public traffic
mcp = FastMCP("Social Publisher MCP", host="0.0.0.0", port=PORT)

#import os
import time
import requests
#from mcp.server.fastmcp import FastMCP
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Render assigns a dynamic port via the PORT environment variable
#PORT = int(os.getenv("PORT", 8000))
#mcp = FastMCP("Social Publisher MCP", host="0.0.0.0", port=PORT)

# --- ENVIRONMENT VARIABLES ---
YT_CLIENT_ID = os.getenv("YT_CLIENT_ID", "")
YT_CLIENT_SECRET = os.getenv("YT_CLIENT_SECRET", "")
YT_REFRESH_TOKEN = os.getenv("YT_REFRESH_TOKEN", "")

IG_USER_ID = os.getenv("IG_USER_ID", "")
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "")

CR_API_KEY = os.getenv("CONTENT_REWARDS_API_KEY", "")
CR_CAMPAIGN_ID = os.getenv("CONTENT_REWARDS_CAMPAIGN_ID", "")


# -------------------------------------------------------------
# TOOL 1: YouTube Shorts Upload
# -------------------------------------------------------------
@mcp.tool()
def post_youtube_short(video_url_or_path: str, title: str, description: str) -> str:
    """Uploads a vertical video to YouTube Shorts and returns the live shorts link."""
    # If a URL is passed, download it temporarily
    temp_file = "temp_video.mp4"
    if video_url_or_path.startswith("http://") or video_url_or_path.startswith("https://"):
        r = requests.get(video_url_or_path, stream=True)
        r.raise_for_status()
        with open(temp_file, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        upload_path = temp_file
    else:
        upload_path = video_url_or_path

    creds = Credentials(
        None,
        refresh_token=YT_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=YT_CLIENT_ID,
        client_secret=YT_CLIENT_SECRET,
    )
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": f"{title} #Shorts"[:100],
            "description": f"{description}\n\n#Shorts #Gaming",
            "categoryId": "20",  # Gaming
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(upload_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = request.execute()

    if os.path.exists(temp_file):
        os.remove(temp_file)

    video_id = response.get("id")
    return f"https://www.youtube.com/shorts/{video_id}"


# -------------------------------------------------------------
# TOOL 2: Instagram Reels Upload
# -------------------------------------------------------------
@mcp.tool()
def post_instagram_reel(video_url: str, caption: str) -> str:
    """Publishes a video URL as an Instagram Reel and returns the live permalink."""
    # Step A: Create container
    url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
    payload = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": IG_ACCESS_TOKEN,
    }
    r = requests.post(url, data=payload)
    r.raise_for_status()
    creation_id = r.json().get("id")

    # Step B: Wait for Instagram video transcoding
    status_url = f"https://graph.facebook.com/v19.0/{creation_id}?fields=status_code&access_token={IG_ACCESS_TOKEN}"
    for _ in range(30):
        time.sleep(5)
        st_res = requests.get(status_url).json()
        status = st_res.get("status_code")
        if status == "FINISHED":
            break
        elif status == "ERROR":
            raise RuntimeError(f"Instagram processing failed: {st_res}")

    # Step C: Publish Media
    pub_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
    pub_res = requests.post(pub_url, data={"creation_id": creation_id, "access_token": IG_ACCESS_TOKEN}).json()
    post_id = pub_res.get("id")

    # Step D: Get live permalink
    permalink_url = f"https://graph.facebook.com/v19.0/{post_id}?fields=permalink&access_token={IG_ACCESS_TOKEN}"
    return requests.get(permalink_url).json().get("permalink")


# -------------------------------------------------------------
# TOOL 3: Content Rewards Submission
# -------------------------------------------------------------
@mcp.tool()
def submit_to_content_rewards(post_url: str, platform: str) -> str:
    """Submits a live YouTube or Instagram link to the Content Rewards campaign within the 30-min window."""
    endpoint = "https://api.contentrewards.com/v1/submissions"
    headers = {
        "Authorization": f"Bearer {CR_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "campaign_id": CR_CAMPAIGN_ID,
        "url": post_url,
        "platform": platform.lower(),
    }
    res = requests.post(endpoint, json=payload, headers=headers, timeout=15)
    return f"HTTP {res.status_code}: {res.text}"


if __name__ == "__main__":
    # Runs using Streamable HTTP / Server-Sent Events (SSE)
    mcp.run(transport="sse")
