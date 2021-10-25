from dataclasses import dataclass, field
from enum import Enum
from functools import partial
from traceback import print_exc
from typing import Optional
import discord
import requests
from yt_dlp import YoutubeDL


class LoopState(Enum):
    OFF = 0
    NOW_PLAYING = 1
    QUEUE = 2


@dataclass
class QueueEntry:

    author: discord.User
    url: str
    audio: discord.FFmpegPCMAudio
    title: str


@dataclass
class MusicState:

    guild_id: int
    voiceclient: Optional[discord.VoiceClient] = None
    queue: list[QueueEntry] = field(default_factory=list)
    now_playing: Optional[QueueEntry] = None
    ls: LoopState = LoopState.OFF


def get_spotify_token(client: str, secret: str):

    resp = requests.post(
        'https://accounts.spotify.com/api/token', auth=(client, secret),
        data={'grant_type': 'client_credentials'}
    )
    if resp.status_code != 200:
        return None

    return resp.json()['access_token']


def handle_spotify(client: str, secret: str, url: str):

    token = get_spotify_token(client, secret)

    item_type = url.split('/')[-2]
    item_id = url.split('/')[-1].split('?')[0]

    if item_type.lower() == 'track':

        resp = requests.get(
            f'https://api.spotify.com/v1/tracks/{item_id}',
            headers={'Authorization': f'Bearer {token}'}
        )

        if resp.status_code != 200:
            return None

        track = resp.json()
        artists = track['artists']

        return (
            f'{track["name"]} '
            f'{artists[0]["name"] if len(artists) > 0 else ""}'
        )

    elif item_type.lower() in ('album', 'playlist'):

        resp = requests.get(
            (
                f'https://api.spotify.com/v1/'
                f'{item_type.lower()}s/{item_id}/tracks'
            ),
            headers={'Authorization': f'Bearer {token}'}
        )

        if resp.status_code != 200:
            return None

        item = resp.json()
        tracks = item['items']

        return [
            (
                f'{track["name"]} '
                f'{track["artists"][0]["name"] if len(track["artists"]) > 0 else ""}'  # noqa: E501
            ) if item_type.lower() == 'album' else (
                f'{track["track"]["name"]} '
                f'{track["track"]["artists"][0]["name"] if len(track["track"]["artists"]) > 0 else ""}'  # noqa: E501
            )
            for track in tracks
        ]


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


def generate_playlist(
    client: str, secret: str, options: dict[str, str], src: str, *args
):

    audio_dl = YoutubeDL(options)

    if 'open.spotify.com' in [s.lower() for s in src.split('/')]:
        tracks = handle_spotify(client, secret, src)

        for t in tracks:

            resp = audio_dl.extract_info(f'ytsearch:{t}', download=False)
            yield resp['entries'][0] if 'entries' in resp else resp

    else:

        for iek, i in audio_dl._ies.items():
            if not i.suitable(src):
                continue
            tid = i.get_temp_id(src)
            if tid is not None:
                ie = audio_dl.get_info_extractor(iek)
                break

        print(f'ie: {ie}; url: {src}')

        extract = ie.extract(src)
        ie_result = ie.extract(extract['url'])

        print(ie_result)

        entries = list(ie_result['entries'])

        for e in entries:
            yield audio_dl.extract_info(
                e['url'], ie_key=e['ie_key'], download=False
            )


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
