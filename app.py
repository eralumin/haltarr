import os
import logging

import qbittorrentapi
import requests

from abc import ABC, abstractmethod
from flask import Flask, request
from deluge_client import DelugeRPCClient
from pysabnzbd import SabnzbdApi

app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Track active playbacks
active_sessions = {}


class Notifier(ABC):
    @abstractmethod
    def send_message(self, message: str):
        pass


class DiscordNotifier(Notifier):
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url

    def send_message(self, message):
        if not self.webhook_url:
            logging.error("Discord Webhook URL is not set.")
            raise ValueError("Discord Webhook URL is not set.")
        data = {"content": message}
        response = requests.post(self.webhook_url, json=data)
        if response.status_code != 204:
            logging.error(f"Failed to send message to Discord: {response.status_code}")
            raise Exception(f"Failed to send message to Discord: {response.status_code}")


class DownloadService(ABC):
    @abstractmethod
    def pause(self):
        pass

    @abstractmethod
    def resume(self):
        pass


class SABnzbdService(DownloadService):
    def __init__(self, host, port, api_key):
        self.client = SabnzbdApi(api_key=api_key, host=f"http://{host}:{port}")

    def pause(self):
        logging.info("Pausing SABnzbd downloads.")
        self.client.pause()

    def resume(self):
        logging.info("Resuming SABnzbd downloads.")
        self.client.resume()


class DelugeService(DownloadService):
    def __init__(self, host, port, username, password):
        self.client = DelugeRPCClient(host, int(port), username, password)
        self.client.connect()

    def pause(self):
        logging.info("Pausing Deluge downloads.")
        self.client.call('core.pause_all_torrents')

    def resume(self):
        logging.info("Resuming Deluge downloads.")
        self.client.call('core.resume_all_torrents')


class QbittorrentService(DownloadService):
    def __init__(self, host, port, username, password):
        self.qbt_client = qbittorrentapi.Client(
            host=host,
            port=port,
            username=username,
            password=password,
        )

    def pause(self):
        logging.info("Pausing qBittorrent downloads.")
        self.client.pausetorrents()

    def resume(self):
        logging.info("Resuming qBittorrent downloads.")
        self.client.resumetorrents()


class MediaServerHandler(ABC):
    """
    Abstract handler for media server events. Each media server implementation
    should inherit from this class.
    """
    def __init__(self, name):
        self.name = name
        self.active_sessions = set()

    @abstractmethod
    def extract_event(self, data):
        pass


class JellyfinHandler(MediaServerHandler):
    def __init__(self):
        super().__init__("jellyfin")

    def extract_event(self, data):
        if "Event" in data and "User" in data:
            event = data['Event']
            user = data['User']['Id']
            if event == "media.play":
                return "play", user
            elif event == "media.stop":
                return "stop", user
        return None, None


class PlexHandler(MediaServerHandler):
    def __init__(self):
        super().__init__("plex")

    def extract_event(self, data):
        if "event" in data and "Account" in data:
            event = data['event']
            user = data['Account']['id']
            if event == "media.play":
                return "play", user
            elif event == "media.stop":
                return "stop", user
        return None, None


class EmbyHandler(MediaServerHandler):
    def __init__(self):
        super().__init__("emby")

    def extract_event(self, data):
        if "NotificationType" in data and "Session" in data:
            event = data['NotificationType']
            user = data['Session']['UserId']
            if event == "playbackstart":
                return "play", user
            elif event == "playbackstop":
                return "stop", user
        return None, None


class MediaSessionManager:
    """
    Manager responsible for tracking active sessions across multiple media servers
    and determining when to pause or resume downloads.
    """
    def __init__(self):
        self.handlers = {
            "jellyfin": JellyfinHandler(),
            "plex": PlexHandler(),
            "emby": EmbyHandler()
        }

    def update_sessions(self, media_server, user, event_type):
        handler = self.handlers.get(media_server)
        if not handler:
            logging.warning(f"Unknown media server: {media_server}")
            return

        if event_type == "play":
            logging.info(f"User {user} started playing media on {media_server}.")
            handler.active_sessions.add(user)
        elif event_type == "stop":
            logging.info(f"User {user} stopped playing media on {media_server}.")
            handler.active_sessions.discard(user)

    def should_resume_downloads(self):
        for handler in self.handlers.values():
            if handler.active_sessions:
                logging.info(f"Active sessions on {handler.name}: {handler.active_sessions}")
                return False

        return True


class DownloadManager:
    """
    Manages pausing and resuming of downloads by communicating with various download services.
    """
    def __init__(self, notifier: Notifier):
        self.notifier = notifier
        self.download_services = self.get_download_services()

    def get_download_services(self):
        services = []
        # SABnzbd
        if os.getenv('SABNZBD_HOST'):
            services.append(SABnzbdService(
                host=os.getenv('SABNZBD_HOST'),
                port=os.getenv('SABNZBD_PORT', '8080'),
                api_key=os.getenv('SABNZBD_API_KEY')
            ))
        # Deluge
        if os.getenv('DELUGE_HOST'):
            services.append(DelugeService(
                host=os.getenv('DELUGE_HOST'),
                port=os.getenv('DELUGE_PORT', '58846'),
                username=os.getenv('DELUGE_USERNAME'),
                password=os.getenv('DELUGE_PASSWORD')
            ))
        # qBittorrent
        if os.getenv('QBITTORRENT_HOST'):
            services.append(QbittorrentService(
                host=os.getenv('QBITTORRENT_HOST'),
                port=os.getenv('QBITTORRENT_PORT', '8080'),
                username=os.getenv('QBITTORRENT_USERNAME'),
                password=os.getenv('QBITTORRENT_PASSWORD')
            ))
        return services

    def pause_downloads(self):
        logging.info("Pausing all download clients.")
        self.notifier.send_message("Media is playing. Pausing all download clients...")
        for service in self.download_services:
            service.pause()

    def resume_downloads(self):
        logging.info("Resuming all download clients.")
        self.notifier.send_message("All media stopped. Resuming all download clients...")
        for service in self.download_services:
            service.resume()


@app.route('/api/v1/playback-events', methods=['POST'])
def playback_events():
    data = request.json
    media_server, user, event_type = None, None, None

    for server, handler in MediaSessionManager().handlers.items():
        event_type, user = handler.extract_event(data)
        if event_type and user:
            media_server = server
            break

    if not media_server:
        logging.warning("Unrecognized event or missing user/server information.")
        return "Unrecognized event", 400

    session_manager = MediaSessionManager()
    session_manager.update_sessions(media_server, user, event_type)

    notifier = DiscordNotifier(webhook_url=os.getenv('DISCORD_WEBHOOK_URL'))
    download_manager = DownloadManager(notifier)

    if event_type == "play":
        download_manager.pause_downloads()
    elif event_type == "stop" and session_manager.should_resume_downloads():
        download_manager.resume_downloads()

    return "OK", 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
