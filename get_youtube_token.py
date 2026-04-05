"""Manual OAuth flow for YouTube with any client type.

Run: python get_youtube_token.py
Then paste the authorization code from your browser's URL bar.
"""

import json

import httpx

with open("client_secrets.json") as f:
    client_config = json.load(f)

CLIENT_ID = client_config["installed"]["client_id"]
CLIENT_SECRET = client_config["installed"]["client_secret"]

SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

auth_url = (
    "https://accounts.google.com/o/oauth2/v2/auth?"
    f"response_type=code&"
    f"client_id={CLIENT_ID}&"
    f"redirect_uri=http://localhost&"
    f"scope={'%20'.join(SCOPES)}&"
    f"access_type=offline&"
    f"prompt=consent"
)

print("\n1. Open this URL:")
print(auth_url)
print("\n2. Authorize, then you'll be redirected to localhost.")
print("   Your browser will fail to load the page — that's fine.")
print("   Copy the 'code' parameter from the URL bar.")

code = input("\n3. Paste the code here: ").strip()
if not code:
    print("No code provided.")
    exit(1)

token_resp = httpx.post(
    "https://oauth2.googleapis.com/token",
    data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "redirect_uri": "http://localhost",
        "grant_type": "authorization_code",
    },
)
body = token_resp.json()

if "refresh_token" in body:
    print(f"\nYour refresh token: {body['refresh_token']}")
else:
    print(f"Error: {body}")
