import os
import logging
import requests
from abc import ABC, abstractmethod
import qbittorrentapi
from deluge_web_client import DelugeWebClient
from flask import Flask, request

app = Flask(__name__)

# Configure Flask app logging
if __name__ != '__main__':
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)

# Abstract Notifier class
class Notifier(ABC):
    @abstractmethod
    def send_message(self, message: str):
        pass


class DiscordNotifier(Notifier):
    def __init__(self, webhook_url, logger):
        self.webhook_url = webhook_url
        self.logger = logger

    def send_message(self, message):
        if not self.webhook_url:
            self.logger.error("Discord Webhook URL is not set.")
            raise ValueError("Discord Webhook URL is not set.")
        data = {"content": message}
        response = requests.post(self.webhook_url, json=data)
        if response.status_code != 204:
            self.logger.error(f"Failed to send message to Discord: {response.status_code}")
            raise Exception(f"Failed to send message to Discord: {response.status_code}")

# Abstract DownloadService class
class DownloadService(ABC):
    def __init__(self, logger):
        self.logger = logger

    @abstractmethod
    def pause(self):
        pass

    @abstractmethod
    def resume(self):
        pass


# Concrete implementations of DownloadService for each client
class SABnzbdService(DownloadService):
    def __init__(self, host, port, api_key, logger):
        super().__init__(logger)
        self.base_url = f"http://{host}:{port}"
        self.api_key = api_key

    def _call_api(self, mode):
        try:
            url = f"{self.base_url}?mode={mode}&apikey={self.api_key}"
            response = requests.get(url)
            if response.status_code == 200:
                self.logger.info(f"SABnzbd {mode} successful.")
            else:
                self.logger.error(f"Failed to {mode} SABnzbd. Status code: {response.status_code}")
        except requests.RequestException as e:
            self.logger.error(f"Error communicating with SABnzbd: {e}")

    def pause(self):
        self.logger.info("Pausing SABnzbd downloads.")
        self._call_api("pause")

    def resume(self):
        self.logger.info("Resuming SABnzbd downloads.")
        self._call_api("resume")


class DelugeService(DownloadService):
    def __init__(self, host, port, password, logger):
        super().__init__(logger)
        url = f"http://{host}:{port}"
        self.client = DelugeWebClient(url=url, password=password)

    def _get_torrent_ids_or_empty_list(self):
        torrents = self.client.get_torrents_status()
        if torrents.result:
            return list(torrents.result.keys())
        return []

    def pause(self):
        self.logger.info("Pausing Deluge torrents.")
        try:
            torrent_ids = self._get_torrent_ids_or_empty_list()
            self.client.pause_torrents(torrent_ids)
        except Exception as e:
            self.logger.error(f"Error pausing torrents: {e}")

    def resume(self):
        self.logger.info("Resuming Deluge torrents.")
        try:
            torrent_ids = self._get_torrent_ids_or_empty_list()
            self.client.resume_torrents(torrent_ids)
        except Exception as e:
            self.logger.error(f"Error resuming torrents: {e}")


class QbittorrentService(DownloadService):
    def __init__(self, host, port, username, password, logger):
        super().__init__(logger)
        self.qbt_client = qbittorrentapi.Client(
            host=host,
            port=port,
            username=username,
            password=password,
        )

    def pause(self):
        self.logger.info("Pausing qBittorrent downloads.")
        self.qbt_client.torrents.pause_all()

    def resume(self):
        self.logger.info("Resuming qBittorrent downloads.")
        self.qbt_client.torrents.resume_all()


# Abstract MediaSessionManager class
class MediaSessionManager(ABC):
    def __init__(self, api_url, api_key, logger):
        self.api_url = api_url
        self.api_key = api_key
        self.logger = logger

    @abstractmethod
    def has_active_sessions(self):
        ...


class JellyfinMediaServer(MediaSessionManager):
    def __init__(self, host, port, api_key, logger):
        api_url = f"http://{host}:{port}"
        super().__init__(api_url, api_key, logger)

    def _fetch_sessions(self):
        headers = {'X-Emby-Token': self.api_key}
        try:
            response = requests.get(f'{self.api_url}/Sessions', headers=headers)
            response.raise_for_status()

            return response.json()

        except requests.RequestException as e:
            self.logger.error(f"Error fetching Jellyfin sessions: {e}")
            return []

    def has_active_sessions(self):
        sessions = self._fetch_sessions()
        for session in sessions:

            if session.get('IsActive'):
                self.logger.info(f"Active session found: User {session['UserName']}, Session ID: {session['Id']}")
                return True

        self.logger.info("No active sessions found.")
        return False


class PlexMediaServer(MediaSessionManager):
    def __init__(self, host, port, api_key, logger):
        api_url = f"http://{host}:{port}/api"
        super().__init__(api_url, api_key, logger)

    def has_active_sessions(self):
        headers = {'X-Plex-Token': self.api_key}
        try:
            response = requests.get(f'{self.api_url}/status/sessions', headers=headers)
            response.raise_for_status()

            json = response.json()
            total_active_sessions = json.get("MediaContainer", {}).get("size", 0)

            return total_active_sessions > 0

        except requests.RequestException as e:
            self.logger.error(f"Error fetching Plex sessions: {e}")
            return False


class EmbyMediaServer(MediaSessionManager):
    def __init__(self, host, port, api_key, logger):
        api_url = f"http://{host}:{port}/api"
        super().__init__(api_url, api_key, logger)

    def _fetch_sessions(self):
        headers = {'X-Emby-Token': self.api_key}
        try:
            response = requests.get(f'{self.api_url}/Sessions', headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            self.logger.error(f"Error fetching Emby sessions: {e}")
            return []


class MediaServerManager:
    def __init__(self, logger):
        self.logger = logger
        self.media_servers = []

        # Initialize Jellyfin if environment variables are set
        if os.getenv('JELLYFIN_HOST'):
            self.media_servers.append(JellyfinMediaServer(
                host=os.getenv('JELLYFIN_HOST'),
                port=os.getenv('JELLYFIN_PORT', '8096'),
                api_key=os.getenv('JELLYFIN_API_KEY'),
                logger=logger
            ))

        # Initialize Plex if environment variables are set
        if os.getenv('PLEX_HOST'):
            self.media_servers.append(PlexMediaServer(
                host=os.getenv('PLEX_HOST'),
                port=os.getenv('PLEX_PORT', '32400'),
                api_key=os.getenv('PLEX_API_KEY'),
                logger=logger
            ))

        # Initialize Emby if environment variables are set
        if os.getenv('EMBY_HOST'):
            self.media_servers.append(EmbyMediaServer(
                host=os.getenv('EMBY_HOST'),
                port=os.getenv('EMBY_PORT', '8096'),
                api_key=os.getenv('EMBY_API_KEY'),
                logger=logger
            ))

    def has_active_sessions(self):
        for media_server in self.media_servers:
            if media_server.has_active_sessions():
                return True
        return False


# DownloadManager to manage download clients
class DownloadManager:
    def __init__(self, notifier: Notifier, logger):
        self.notifier = notifier
        self.logger = logger
        self.download_services = self._initialize_services()

    def _initialize_services(self):
        services = []
        if os.getenv('SABNZBD_HOST'):
            services.append(SABnzbdService(
                host=os.getenv('SABNZBD_HOST'),
                port=os.getenv('SABNZBD_PORT', '8080'),
                api_key=os.getenv('SABNZBD_API_KEY'),
                logger=self.logger
            ))
        if os.getenv('DELUGE_HOST'):
            services.append(DelugeService(
                host=os.getenv('DELUGE_HOST'),
                port=os.getenv('DELUGE_PORT', '8112'),
                password=os.getenv('DELUGE_PASSWORD'),
                logger=self.logger
            ))
        if os.getenv('QBITTORRENT_HOST'):
            services.append(QbittorrentService(
                host=os.getenv('QBITTORRENT_HOST'),
                port=os.getenv('QBITTORRENT_PORT', '8080'),
                username=os.getenv('QBITTORRENT_USERNAME'),
                password=os.getenv('QBITTORRENT_PASSWORD'),
                logger=self.logger
            ))
        return services

    def pause_downloads(self):
        self.logger.info("Pausing all download clients.")
        self.notifier.send_message("Media is playing. Pausing all download clients...")
        for service in self.download_services:
            service.pause()

    def resume_downloads(self):
        self.logger.info("Resuming all download clients.")
        self.notifier.send_message("All media stopped. Resuming all download clients...")
        for service in self.download_services:
            service.resume()


# Initialize the notifier, media server manager, and download manager
notifier = DiscordNotifier(webhook_url=os.getenv('DISCORD_WEBHOOK_URL'), logger=app.logger)
media_server_manager = MediaServerManager(app.logger)
download_manager = DownloadManager(notifier, app.logger)


@app.route('/api/v1/playback-events', methods=['POST'])
def playback_events():
    app.logger.info(f"Received JSON payload: {request.json}")

    if media_server_manager.has_active_sessions():
        download_manager.pause_downloads()
    else:
        download_manager.resume_downloads()

    return "OK", 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
