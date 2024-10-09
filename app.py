import os

from abc import ABC, abstractmethod

import qbittorrentapi
import requests

from deluge_web_client import DelugeWebClient
from flask import Flask, request

app = Flask(__name__)

# Setup logging for the app
app.logger.setLevel('INFO')

# Track active playbacks
active_sessions = {}


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


class DownloadService(ABC):
    def __init__(self, logger):
        self.logger = logger

    @abstractmethod
    def pause(self):
        pass

    @abstractmethod
    def resume(self):
        pass


class SABnzbdService(DownloadService):
    def __init__(self, host, port, api_key, logger):
        super().__init__(logger)
        self.base_url=f"http://{host}:{port}"

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

        url=f"http://{host}:{port}"
        self.client = DelugeWebClient(url=url, password=password)

    def _get_torrent_ids_or_empty_list(self):
        torrents = self.client.get_torrents_status()
        if torrents.result:
            return list(torrents.result.keys())

        return list()

    def pause(self):
        self.logger.info("Pausing Deluge torrents")
        try:
            torrent_ids = self._get_torrent_ids_or_empty_list()
            self.client.pause_torrents(torrent_ids)
        except Exception as e:
            self.logger.error(f"Error pausing torrents: {e}")

    def resume(self):
        self.logger.info("Resuming Deluge torrents")
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


class MediaServerHandler(ABC):
    def __init__(self, logger, name):
        self.logger = logger
        self.name = name
        self.active_sessions = set()

    @abstractmethod
    def extract_event(self, data):
        pass


class JellyfinHandler(MediaServerHandler):
    def __init__(self, logger):
        super().__init__(logger=logger, name="jellyfin")

    def extract_event(self, data):
        if "Event" in data and "User" in data:
            event = data['Event']
            user = data['User']['Id']
            if event == "media.play":
                self.logger.info(f"Jellyfin: User {user} started playing media.")
                return "play", user
            elif event == "media.stop":
                self.logger.info(f"Jellyfin: User {user} stopped playing media.")
                return "stop", user

        self.logger.warning("Jellyfin: No valid event found in data.")
        return None, None


class PlexHandler(MediaServerHandler):
    def __init__(self, logger):
        super().__init__(logger=logger, name="plex")

    def extract_event(self, data):
        if "event" in data and "Account" in data:
            event = data['event']
            user = data['Account']['id']
            if event == "media.play":
                self.logger.info(f"Plex: User {user} started playing media.")
                return "play", user
            elif event == "media.stop":
                self.logger.info(f"Plex: User {user} stopped playing media.")
                return "stop", user

        self.logger.warning("Plex: No valid event found in data.")
        return None, None


class EmbyHandler(MediaServerHandler):
    def __init__(self, logger):
        super().__init__(logger=logger, name="emby")

    def extract_event(self, data):
        if "NotificationType" in data and "Session" in data:
            event = data['NotificationType']
            user = data['Session']['UserId']
            if event == "playbackstart":
                self.logger.info(f"Emby: User {user} started playing media.")
                return "play", user
            elif event == "playbackstop":
                self.logger.info(f"Emby: User {user} stopped playing media.")
                return "stop", user

        self.logger.warning("Emby: No valid event found in data.")
        return None, None


class MediaSessionManager:
    def __init__(self, logger):
        self.logger = logger
        self.handlers = {
            "jellyfin": JellyfinHandler(logger),
            "plex": PlexHandler(logger),
            "emby": EmbyHandler(logger)
        }

    def update_sessions(self, media_server, user, event_type):
        handler = self.handlers.get(media_server)
        if not handler:
            self.logger.warning(f"Unknown media server: {media_server}")
            return

        if event_type == "play":
            self.logger.info(f"User {user} started playing media on {media_server}.")
            handler.active_sessions.add(user)
        elif event_type == "stop":
            self.logger.info(f"User {user} stopped playing media on {media_server}.")
            handler.active_sessions.discard(user)

    def should_resume_downloads(self):
        for handler in self.handlers.values():
            if handler.active_sessions:
                self.logger.info(f"Active sessions on {handler.name}: {handler.active_sessions}")
                return False
        return True


class DownloadManager:
    def __init__(self, notifier: Notifier, logger):
        self.notifier = notifier
        self.logger = logger
        self.download_services = self.get_download_services()

    def get_download_services(self):
        services = []
        # SABnzbd
        if os.getenv('SABNZBD_HOST'):
            services.append(SABnzbdService(
                host=os.getenv('SABNZBD_HOST'),
                port=os.getenv('SABNZBD_PORT', '8080'),
                api_key=os.getenv('SABNZBD_API_KEY'),
                logger=self.logger
            ))
        # Deluge
        if os.getenv('DELUGE_HOST'):
            services.append(DelugeService(
                host=os.getenv('DELUGE_HOST'),
                port=os.getenv('DELUGE_PORT', '8112'),
                password=os.getenv('DELUGE_PASSWORD'),
                logger=self.logger
            ))
        # qBittorrent
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


# Initialize download clients and media services once
notifier = DiscordNotifier(webhook_url=os.getenv('DISCORD_WEBHOOK_URL'), logger=app.logger)
download_manager = DownloadManager(notifier, app.logger)
session_manager = MediaSessionManager(app.logger)


@app.route('/api/v1/playback-events', methods=['POST'])
def playback_events():
    app.logger.info(f"Received JSON payload: {request.json}")

    data = request.json
    media_server, user, event_type = None, None, None

    app.logger.info("Evaluating media server handlers for event extraction...")

    for server, handler in session_manager.handlers.items():
        event_type, user = handler.extract_event(data)
        if event_type and user:
            media_server = server
            break

    if not media_server:
        app.logger.warning("Unrecognized event or missing user/server information.")
        return "Unrecognized event", 400

    app.logger.info(f"Extracted event: {event_type} from {media_server} for user {user}")
    session_manager.update_sessions(media_server, user, event_type)

    if event_type == "play":
        download_manager.pause_downloads()
    elif event_type == "stop" and session_manager.should_resume_downloads():
        download_manager.resume_downloads()

    return "OK", 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
