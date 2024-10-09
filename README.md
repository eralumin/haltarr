<p align="center">
  <img src="./icon.png" alt="Haltarr Icon" width="200"/>
</p>

# Haltarr

**Haltarr** is a Python Flask-based service that pauses or resumes download clients (SABnzbd, Deluge, qBitTorrent) when media is played or stopped on media servers (Jellyfin, Plex,Emby). It also notifies Discord of these events via webhooks.

## Features
- Pauses/Resumes SABnzbd, qBitTorrent and Deluge download clients based on media playback in Jellyfin, Plex and Emby.
- Sends notifications to Discord.

## Summary
- [Setup](#setup)
  - [Environment Variables](#environment-variables)
  - [Running the App Locally](#running-the-app-locally)
  - [Running with Docker](#running-with-docker)
- [Adding Webhooks to Jellyfin, Plex, and Emby](#adding-webhooks-to-jellyfin-plex-and-emby)
  - [Jellyfin Webhook Setup](#jellyfin-webhook-setup)
  - [Plex Webhook Setup](#plex-webhook-setup)
  - [Emby Webhook Setup](#emby-webhook-setup)

## Setup

### Environment Variables
- `DISCORD_WEBHOOK_URL`: Your Discord webhook URL to send notifications.
- `SABNZBD_API_KEY`: API key for SABnzbd.
- `DELUGE_HOST`: Host for Deluge.
- `DELUGE_PORT`: Port for Deluge.
- `DELUGE_USERNAME`: Username for Deluge.
- `DELUGE_PASSWORD`: Password for Deluge.

### Running the app locally
1. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the app:
    ```bash
    python app.py
    ```

### Running with Docker
Build and run the Docker container:
```bash
    docker build -t eralumin/controllarr .
    docker run -d -p 5000:5000 --env-file .env eralumin/controllarr
```

### Adding Webhooks to Jellyfin, Plex, and Emby

#### Jellyfin Webhook Setup
To configure Jellyfin to send media events to Haltarr:
1. Open Jellyfin and go to Dashboard.
2. Navigate to Notifications and click on the Webhook tab.
3. Add a new webhook with the following information:
  - **Webhook Name:** Haltarr
  - **Webhook URL:** http://Haltarr:5000/api/v1/media-events
  - **Notification Types:**
    - `Playback Start`
    - `Playback Stop`
4. Click Save to apply the webhook.

#### Plex Webhook Setup
To configure Plex to send media events to Haltarr:

1. Open Plex and go to Settings.
2. Navigate to Webhooks under the Account settings.
3. Click on Add Webhook and enter the following URL:
  - **Webhook URL:** http://Haltarr:5000/api/v1/media-events
4. Click Save to add the webhook.

#### Emby Webhook Setup
To configure Emby to send media events to Haltarr:

1. Open Emby and go to Settings.
2. Navigate to Webhooks in the settings menu.
3. Add a new webhook with the following details:
  - **Webhook URL:** http://Haltarr:5000/api/v1/media-events
4. Select the appropriate events to track:
  - `playbackstart`
  - `playbackstop`
5. Click Save to apply the webhook.
