from enum import Enum
from functools import partial
from traceback import print_exc
import discord
import requests
from yt_dlp import YoutubeDL


class LoopState(Enum):
    OFF = 0
    NOW_PLAYING = 1
    QUEUE = 2


class QueueEntry:

    author: discord.User
    url: str
    audio: discord.FFmpegPCMAudio
    title: str

    def __init__(
        self, author: discord.User, url: str,
        audio: discord.FFmpegPCMAudio, title: str
    ):
        self.author = author
        self.url = url
        self.audio = audio
        self.title = title


class MusicState:

    guild_id: int
    voiceclient: discord.VoiceClient
    queue: list[QueueEntry]
    now_playing: QueueEntry
    ls: LoopState

    def __init__(
        self, guild_id: int, voiceclient: discord.VoiceClient = None,
        queue: list[QueueEntry] = None, now_playing: QueueEntry = None,
        ls: LoopState = LoopState.OFF
    ):

        self.guild_id = guild_id
        self.voiceclient = voiceclient
        self.queue = queue or []
        self.now_playing = now_playing
        self.ls = ls


def handle_spotify(client: str, secret: str, url: str):

    resp = requests.post(
        'https://accounts.spotify.com/api/token', auth=(client, secret),
        data={'grant_type': 'client_credentials'}
    )
    if resp.status_code != 200:
        return None

    token = resp.json()['access_token']

    track_id = url.split('/')[-1].split('?')[0]

    resp = requests.get(
        f'https://api.spotify.com/v1/tracks/{track_id}',
        headers={'Authorization': f'Bearer {token}'}
    )

    if resp.status_code != 200:
        return None

    track = resp.json()
    artists = track['artists']

    return f'{track["name"]} {artists[0]["name"] if len(artists) > 0 else ""}'


def get_audio(options: dict[str, str], src: str, *args):
    kw: str = ' '.join([src, *args])
    try:
        audio_dl = YoutubeDL(options)
        resp = audio_dl.extract_info(
            (
                f'ytsearch:{kw}'
                if 'www.youtube.com' not in [s.lower() for s in kw.split('/')]
                else kw
            ), download=False
        )
        return resp['entries'][0] if 'entries' in resp else resp
    except Exception:
        print_exc()
        return None


def ffmpeg_options(seek: int = None):
    if seek:
        return {
            'before_options': (
                '-reconnect 1 -reconnect_streamed 1 '
                f'-reconnect_delay_max 5 -ss {seek}'
            ), 'options': '-vn'
        }
    return {
        'before_options': (
            '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
        ), 'options': '-vn'
    }


def apply_context(func, ctx):
    return partial(func, ctx)
