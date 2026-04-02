"""One-time script to get YouTube OAuth refresh token.

Usage:
    pip install google-auth-oauthlib google-auth-httplib2
    python scripts/get_youtube_token.py

Follow the browser prompt to authorize, then paste the refresh token into .env
"""

from google_auth_oauthlib.flow import InstalledAppFlow

# The scope we need for YouTube uploads
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main():
    print("YouTube OAuth Setup")
    print("=" * 40)
    print()

    # Get OAuth credentials from Google Cloud Console
    # https://console.cloud.google.com/apis/credentials
    print("Step 1: Create OAuth credentials at:")
    print("  https://console.cloud.google.com/apis/credentials")
    print("  - Application type: Desktop app")
    print("  - Download the JSON file and note the path")
    print()

    import os
    client_secrets = os.environ.get("YOUTUBE_CLIENT_SECRETS", "")
    if not client_secrets:
        client_secrets = input("Path to client_secrets.json (or path to dir): ").strip()

    flow = InstalledAppFlow.from_client_secrets_file(
        client_secrets,
        scopes=SCOPES,
        redirect_uri="urn:ietf:wg:oauth:2.0:oob",
    )

    flow.run_local_server(port=8080)
    creds = flow.credentials

    print()
    print("=" * 40)
    print("Your refresh token:")
    print(creds.refresh_token)
    print()
    print("Add these to your .env:")
    print(f"YOUTUBE_CLIENT_ID={creds.client_id}")
    print(f"YOUTUBE_CLIENT_SECRET={creds.client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")


if __name__ == "__main__":
    main()
