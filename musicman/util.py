from enum import Enum
from functools import partial
import discord
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
        queue: list[QueueEntry] = [], now_playing: QueueEntry = None,
        ls: LoopState = LoopState.OFF
    ):

        self.guild_id = guild_id
        self.voiceclient = voiceclient
        self.queue = queue
        self.now_playing = now_playing
        self.ls = ls


def get_audio(options: dict[str, str], src: str, *args):
    kw: str = ' '.join([src, *args])
    try:
        audio_dl = YoutubeDL(options)
        resp = audio_dl.extract_info(
            f'ytsearch:{kw}', download=False
        )['entries'][0]
        return resp
    except Exception:
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
