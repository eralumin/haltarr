<p align="center">
  <img src="./icon.png" alt="Haltarr Icon" width="200"/>
</p>

# Haltarr

**Haltarr** is a service that pauses or resumes download clients (SABnzbd, Deluge, qBitTorrent) when there is activity on media servers (Jellyfin, Plex, Emby). It also notifies Discord of these events via webhooks.

## Features
- Pauses/Resumes SABnzbd, qBitTorrent and Deluge download clients based on activiry from Jellyfin, Plex and Emby.
- Sends notifications to Discord.

## Summary
- [Environment Variables](#environment-variables)
- [Running the App Locally](#running-the-app-locally)
- [Running with Docker](#running-with-docker)
- [Setup Download Clients](#setup-download-clients):
  - [Setup Deluge](#setup-deluge)

## Environment Variables
Set the following environment variables to configure Haltarr:

- `CHECK_INTERVAL`: Interval between each Media Server activity check in seconds (default: `10`).

### Media Servers
- `JELLYFIN_HOST`: Hostname or IP of your Jellyfin server.
- `JELLYFIN_PORT`: Port for Jellyfin (default: `8096`).
- `JELLYFIN_API_KEY`: API key for Jellyfin.
  
- `PLEX_HOST`: Hostname or IP of your Plex server.
- `PLEX_PORT`: Port for Plex (default: `32400`).
- `PLEX_API_KEY`: API key for Plex.
  
- `EMBY_HOST`: Hostname or IP of your Emby server.
- `EMBY_PORT`: Port for Emby (default: `8096`).
- `EMBY_API_KEY`: API key for Emby.

### Download Clients
- `SABNZBD_HOST`: Hostname or IP of your SABnzbd server.
- `SABNZBD_PORT`: Port for SABnzbd (default: `8080`).
- `SABNZBD_API_KEY`: API key for SABnzbd.

- `DELUGE_HOST`: Hostname or IP of your Deluge server.
- `DELUGE_PORT`: RPC Port for Deluge (default: `58846`).
- `DELUGE_USERNAME`: Username for Deluge.
- `DELUGE_PASSWORD`: Password for Deluge.

- `QBITTORRENT_HOST`: Hostname or IP of your qBitTorrent server.
- `QBITTORRENT_PORT`: Port for qBitTorrent (default: `8080`).
- `QBITTORRENT_USERNAME`: Username for qBitTorrent.
- `QBITTORRENT_PASSWORD`: Password for qBitTorrent.


## Running the app locally
1. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the app:
    ```bash
    python app.py
    ```

## Running with Docker
Build and run the Docker container:
```bash
    docker build -t eralumin/haltarr .
    docker run -d --env-file .env eralumin/haltarr
```

## Setup Download Clients

### Setup Deluge
In order to use **Deluge** with **Haltarr**, you need to configure the Deluge daemon to enable remote access via RPC. This will allow **Haltarr** to control torrent downloads by pausing and resuming them based on media server activity.

1. **Enable the Deluge Daemon**
   
   Ensure that the Deluge daemon (`deluged`) is running,   as this is required for the RPC interface to function:

   ```bash
   deluged
   ```
2. **Enable Remote Connections**
   
   You need to allow remote connections to the Deluge daemon.

   - Via the GTK Client:
     1. Open the Deluge GTK client.
     2. Go to Preferences → Daemons.
     3. Check the box labeled Allow Remote Connections.
   - Manually in the Configuration File:
     1. Open the Deluge configuration file located at `~/.config/deluge/core.conf`.
     2. Find the "allow_remote" setting and ensure it is  set to true:
        ```json
        "allow_remote": true,
        ```
     3. Save the file and restart the Deluge daemon again:
        ```bash
        pkill deluged
        deluged

3. **Configure Authentication for RPC**
   
   Deluge uses an auth file for authentication when accessing the RPC interface. Here’s how to set it up:

   1. Open the auth file in your Deluge configuration directory:
      - On Linux: `~/.config/deluge/auth`
      - On Windows: `%APPDATA%\deluge\auth`
      - On Docker: `/config/auth`
   2. Add a new line to the file in the following format:
      ```makefile
      # username:password:level
      haltarruser:yourpassword:5
      ```

      Here, username is the username you will use to access RPC, password is the chosen password, and 10 is the access level (admin).

    3. Save the file and restart the Deluge daemon again:
       ```bash
       pkill deluged
       deluged
       ```
