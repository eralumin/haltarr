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

## Setup

### Environment Variables
Set the following environment variables to configure Haltarr:

#### Media Servers
- `JELLYFIN_HOST`: Hostname or IP of your Jellyfin server.
- `JELLYFIN_PORT`: Port for Jellyfin (default: `8096`).
- `JELLYFIN_API_KEY`: API key for Jellyfin.
  
- `PLEX_HOST`: Hostname or IP of your Plex server.
- `PLEX_PORT`: Port for Plex (default: `32400`).
- `PLEX_API_KEY`: API key for Plex.
  
- `EMBY_HOST`: Hostname or IP of your Emby server.
- `EMBY_PORT`: Port for Emby (default: `8096`).
- `EMBY_API_KEY`: API key for Emby.

#### Download Clients
- `SABNZBD_HOST`: Hostname or IP of your SABnzbd server.
- `SABNZBD_PORT`: Port for SABnzbd (default: `8080`).
- `SABNZBD_API_KEY`: API key for SABnzbd.

- `DELUGE_HOST`: Hostname or IP of your Deluge server.
- `DELUGE_PORT`: Port for Deluge (default: `8112`).
- `DELUGE_PASSWORD`: Password for Deluge.

- `QBITTORRENT_HOST`: Hostname or IP of your qBitTorrent server.
- `QBITTORRENT_PORT`: Port for qBitTorrent (default: `8080`).
- `QBITTORRENT_USERNAME`: Username for qBitTorrent.
- `QBITTORRENT_PASSWORD`: Password for qBitTorrent.


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
