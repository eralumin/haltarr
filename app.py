import os
import logging
import time

from abc import ABC, abstractmethod

import requests
import qbittorrentapi

from deluge_client import DelugeRPCClient


# Configure Python built-in logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Notifier(ABC):
    @abstractmethod
    def send_message(self, title: str, message: str):
        pass


class DiscordNotifier(Notifier):
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url

    def send_message(self, title, message):
        if not self.webhook_url:
            logger.error("Discord Webhook URL is not set.")
            raise ValueError("Discord Webhook URL is not set.")

        data = {
            "content": None,
            "embeds": [
                {
                    "title": title,
                    "description": message,
                    "color": 5814783
                }
            ],
            "attachments": []
        }

        response = requests.post(self.webhook_url, json=data)
        if response.status_code != 204:
            logger.error(f"Failed to send message to Discord: {response.status_code}")
            raise Exception(f"Failed to send message to Discord: {response.status_code}")


class DownloadService(ABC):
    def __init__(self):
        pass

    @abstractmethod
    def pause(self):
        pass

    @abstractmethod
    def resume(self):
        pass


class DelugeService(DownloadService):
    def __init__(self, host, port, username, password):
        super().__init__()
        self.client = DelugeRPCClient(host, port, username, password)

    def connect(self):
        try:
            self.client.connect()
            logger.info("Connected to Deluge daemon successfully.")
        except Exception as e:
            logger.error(f"Error connecting to Deluge daemon: {e}")
            raise

    def pause(self):
        try:
            logger.info("Pausing all torrents on Deluge...")
            self.connect()

            self.client.call('core.pause_all_torrents')
            logger.info("All torrents paused successfully on Deluge.")
        except Exception as e:
            logger.error(f"Error pausing all torrents on Deluge: {e}")

    def resume(self):
        try:
            logger.info("Resuming all torrents on Deluge...")
            self.connect()

            self.client.call('core.resume_all_torrents')
            logger.info("All torrents resumed successfully on Deluge.")
        except Exception as e:
            logger.error(f"Error resuming all torrents on Deluge: {e}")


class QbittorrentService(DownloadService):
    def __init__(self, host, port, username, password):
        super().__init__()
        self.qbt_client = qbittorrentapi.Client(
            host=host,
            port=port,
            username=username,
            password=password,
        )

    def pause(self):
        logger.info("Pausing qBittorrent downloads.")
        self.qbt_client.torrents.pause_all()

    def resume(self):
        logger.info("Resuming qBittorrent downloads.")
        self.qbt_client.torrents.resume_all()


class SABnzbdService(DownloadService):
    def __init__(self, host, port, api_key):
        super().__init__()
        self.base_url = f"http://{host}:{port}/api"
        self.api_key = api_key

    def _call_api(self, mode):
        try:
            params = {
                "mode": mode,
                "apikey": self.api_key
            }
            response = requests.get(self.base_url, params=params)

            if response.status_code == 200:
                logger.info(f"SABnzbd {mode} successful.")
            else:
                logger.error(f"Failed to {mode} SABnzbd. Status code: {response.status_code}")
        except requests.RequestException as e:
            logger.error(f"Error communicating with SABnzbd: {e}")

    def pause(self):
        logger.info("Pausing SABnzbd downloads.")
        self._call_api("pause")

    def resume(self):
        logger.info("Resuming SABnzbd downloads.")
        self._call_api("resume")


class MediaSessionManager(ABC):
    def __init__(self, api_url, api_key):
        self.api_url = api_url
        self.api_key = api_key

    @abstractmethod
    def has_active_sessions(self):
        pass


class JellyfinMediaServer(MediaSessionManager):
    def __init__(self, host, port, api_key):
        api_url = f"http://{host}:{port}"
        super().__init__(api_url, api_key)

    def _fetch_sessions(self):
        headers = {'X-Emby-Token': self.api_key}
        try:
            response = requests.get(f'{self.api_url}/Sessions', headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Error fetching Jellyfin sessions: {e}")
            return []

    def has_active_sessions(self):
        sessions = self._fetch_sessions()
        for session in sessions:
            if session.get('IsActive'):
                logger.info(f"Active session found: User {session['UserName']}, Session ID: {session['Id']}")
                return True
        logger.info("No active sessions found.")
        return False


class PlexMediaServer(MediaSessionManager):
    def __init__(self, host, port, api_key):
        api_url = f"http://{host}:{port}/api"
        super().__init__(api_url, api_key)

    def has_active_sessions(self):
        headers = {'X-Plex-Token': self.api_key}
        try:
            response = requests.get(f'{self.api_url}/status/sessions', headers=headers)
            response.raise_for_status()
            json = response.json()
            total_active_sessions = json.get("MediaContainer", {}).get("size", 0)
            return total_active_sessions > 0
        except requests.RequestException as e:
            logger.error(f"Error fetching Plex sessions: {e}")
            return False


class EmbyMediaServer(MediaSessionManager):
    def __init__(self, host, port, api_key):
        api_url = f"http://{host}:{port}/api"
        super().__init__(api_url, api_key)

    def has_active_sessions(self):
        headers = {'X-Emby-Token': self.api_key}
        try:
            response = requests.get(f'{self.api_url}/Sessions', headers=headers)
            response.raise_for_status()
            return len(response.json()) > 0
        except requests.RequestException as e:
            logger.error(f"Error fetching Emby sessions: {e}")
            return False


class MediaServerManager:
    def __init__(self):
        self.media_servers = []
        self.has_already_activity = False

        # Initialize Jellyfin if environment variables are set
        if os.getenv('JELLYFIN_HOST'):
            self.media_servers.append(JellyfinMediaServer(
                host=os.getenv('JELLYFIN_HOST'),
                port=os.getenv('JELLYFIN_PORT', '8096'),
                api_key=os.getenv('JELLYFIN_API_KEY')
            ))

        # Initialize Plex if environment variables are set
        if os.getenv('PLEX_HOST'):
            self.media_servers.append(PlexMediaServer(
                host=os.getenv('PLEX_HOST'),
                port=os.getenv('PLEX_PORT', '32400'),
                api_key=os.getenv('PLEX_API_KEY')
            ))

        # Initialize Emby if environment variables are set
        if os.getenv('EMBY_HOST'):
            self.media_servers.append(EmbyMediaServer(
                host=os.getenv('EMBY_HOST'),
                port=os.getenv('EMBY_PORT', '8096'),
                api_key=os.getenv('EMBY_API_KEY')
            ))

    def has_active_sessions(self):
        for media_server in self.media_servers:
            if media_server.has_active_sessions():
                return True
        return False

    def check_and_notify(self, download_manager):
        has_active_sessions = self.has_active_sessions()
        is_activity_just_started =  has_active_sessions and not self.has_already_activity
        is_activity_just_stopped = not has_active_sessions and self.has_already_activity

        if is_activity_just_started:
            self.has_already_activity = True
            download_manager.pause_downloads()

        elif is_activity_just_stopped:
            self.has_already_activity = False
            download_manager.resume_downloads()


class DownloadManager:
    def __init__(self, notifier: Notifier):
        self.notifier = notifier
        self.download_services = self._initialize_services()

    def _initialize_services(self):
        services = []
        if os.getenv('DELUGE_HOST'):
            services.append(DelugeService(
                host=os.getenv('DELUGE_HOST'),
                port=os.getenv('DELUGE_PORT', '58846'),
                username=os.getenv('DELUGE_USERNAME'),
                password=os.getenv('DELUGE_PASSWORD')
            ))
        if os.getenv('QBITTORRENT_HOST'):
            services.append(QbittorrentService(
                host=os.getenv('QBITTORRENT_HOST'),
                port=os.getenv('QBITTORRENT_PORT', '8080'),
                username=os.getenv('QBITTORRENT_USERNAME'),
                password=os.getenv('QBITTORRENT_PASSWORD')
            ))
        if os.getenv('SABNZBD_HOST'):
            services.append(SABnzbdService(
                host=os.getenv('SABNZBD_HOST'),
                port=os.getenv('SABNZBD_PORT', '8080'),
                api_key=os.getenv('SABNZBD_API_KEY')
            ))

        return services

    def pause_downloads(self):
        logger.info("Pausing all download clients.")
        self.notifier.send_message(
            title="Activity on Media Servers.",
            message="Pausing all download clients..."
        )

        for service in self.download_services:
            service.pause()

    def resume_downloads(self):
        logger.info("Resuming all download clients.")
        self.notifier.send_message(
            title="No activity on Media Servers.",
            message="Resuming all download clients..."
        )

        for service in self.download_services:
            service.resume()


def main():
    notifier = DiscordNotifier(webhook_url=os.getenv('DISCORD_WEBHOOK_URL'))
    media_server_manager = MediaServerManager()
    download_manager = DownloadManager(notifier)

    # Interval for checking sessions
    check_interval = int(os.getenv('CHECK_INTERVAL', 10))

    while True:
        logger.info("Checking media server sessions...")
        media_server_manager.check_and_notify(download_manager)
        logger.info(f"Sleeping for {check_interval} seconds.")
        time.sleep(check_interval)


if __name__ == '__main__':
    main()
