import os
import requests
import logging

from deluge_client import DelugeRPCClient
from flask import Flask, request
from pysabnzbd import Sabnzbd
from qbittorrent import Client

app = Flask(__name__)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class DiscordNotifier:
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


class SABnzbdService:
    def __init__(self, host, port, api_key):
        self.host = host
        self.port = port
        self.api_key = api_key
        self.client = self._get_client()

    def _get_client(self):
        return Sabnzbd(api_key=self.api_key, host=f"http://{self.host}:{self.port}")

    def pause(self):
        logging.info("Pausing SABnzbd downloads.")
        self.client.pause()

    def resume(self):
        logging.info("Resuming SABnzbd downloads.")
        self.client.resume()


class DelugeService:
    def __init__(self, host, port, username, password):
        self.host = host
        self.port = int(port)
        self.username = username
        self.password = password
        self.client = self._get_client()

    def _get_client(self):
        client = DelugeRPCClient(self.host, self.port, self.username, self.password)
        client.connect()
        return client

    def pause(self):
        logging.info("Pausing Deluge downloads.")
        self.client.call('core.pause_all_torrents')

    def resume(self):
        logging.info("Resuming Deluge downloads.")
        self.client.call('core.resume_all_torrents')


class QbittorrentService:
    def __init__(self, host, username, password):
        self.host = host
        self.username = username
        self.password = password
        self.client = self._get_client()

    def _get_client(self):
        client = Client(self.host)
        client.login(self.username, self.password)
        return client

    def pause(self):
        logging.info("Pausing qBittorrent downloads.")
        self.client.pausetorrents()

    def resume(self):
        logging.info("Resuming qBittorrent downloads.")
        self.client.resumetorrents()


def get_event_type(data):
    # For Jellyfin
    if "Event" in data:
        event = data['Event']
        if event == "media.play":
            return "play"
        elif event == "media.stop":
            return "stop"

    # For Plex
    if "event" in data:
        event = data['event']
        if event == "media.play":
            return "play"
        elif event == "media.stop":
            return "stop"

    # For Emby
    if "NotificationType" in data:
        event = data['NotificationType']
        if event == "playbackstart":
            return "play"
        elif event == "playbackstop":
            return "stop"

    return None


def get_download_services():
    download_services = []

    # SABnzbd
    sabnzbd_host = os.getenv('SABNZBD_HOST')
    if sabnzbd_host:
        logging.info("Initializing SABnzbd service.")
        download_services.append(SABnzbdService(
            host=sabnzbd_host,
            port=os.getenv('SABNZBD_PORT', '8080'),
            api_key=os.getenv('SABNZBD_API_KEY')
        ))

    # Deluge
    deluge_host = os.getenv('DELUGE_HOST')
    if deluge_host:
        logging.info("Initializing Deluge service.")
        download_services.append(DelugeService(
            host=deluge_host,
            port=os.getenv('DELUGE_PORT'),
            username=os.getenv('DELUGE_USERNAME'),
            password=os.getenv('DELUGE_PASSWORD')
        ))

    # qBittorrent
    qbittorrent_host = os.getenv('QBITTORRENT_HOST')
    if qbittorrent_host:
        logging.info("Initializing qBittorrent service.")
        download_services.append(QbittorrentService(
            host=qbittorrent_host,
            username=os.getenv('QBITTORRENT_USERNAME'),
            password=os.getenv('QBITTORRENT_PASSWORD')
        ))

        return download_services

@app.route('/media-webhook', methods=['POST'])
def media_webhook():
    data = request.json
    event = get_event_type(data)

    download_services = get_download_services()
    notifier = DiscordNotifier(webhook_url=os.getenv('DISCORD_WEBHOOK_URL'))

    if event == "play":
        logging.info("Media play event received. Pausing all download clients.")
        notifier.send_message("Media is playing. Pausing all download clients...")
        for download_service in download_services:
            download_service.pause()

    elif event == "stop":
        logging.info("Media stop event received. Resuming all download clients.")
        notifier.send_message("Media has stopped. Resuming all download clients...")
        for download_service in download_services:
            download_service.resume()

    return "OK", 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
