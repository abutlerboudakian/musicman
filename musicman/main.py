from datetime import datetime as dt
import os
import discord
from discord.ext import commands
from discord.player import FFmpegOpusAudio
from dotenv import load_dotenv
from pytimeparse.timeparse import timeparse
from musicman.music_utils import get_audio

class QueueEntry:

    author: discord.User
    audio: discord.FFmpegOpusAudio

    def __init__(self, author: discord.User, audio: discord.FFmpegOpusAudio, fname: str):
        self.author = author
        self.audio = audio
        self.fname = fname

load_dotenv()
TOKEN = os.getenv('ACCESS_TOKEN')
OUT_PATH = os.getenv('TMP_AUDIO_PATH')

bot = commands.Bot(command_prefix='!')
voiceclient: discord.VoiceClient = None
queue: list[QueueEntry] = []
now_playing: QueueEntry = None

def play_next(error):

    global now_playing
    global voiceclient
    global queue

    if len(queue) > 0:

        now_playing = queue.pop()
        voiceclient.play(now_playing.audio, after=play_next)

@bot.command(name='connect')
async def connect(ctx: commands.Context, *args):

    global voiceclient
    global queue

    channel: discord.VoiceChannel = ctx.author.voice.channel

    if channel:
        voiceclient = await channel.connect()

        await ctx.send(f'musicman connected to {channel.name}')

        if len(queue) > 0:
            play_next(None)

    else:
        await ctx.send(f'{ctx.author.name} is not in a voice channel')


@bot.command(name='play')
async def play(ctx: commands.Context, src: str, *args):

    global voiceclient
    global queue
    global now_playing
    global OUT_PATH

    if not voiceclient:
        await connect(ctx, *args)

    if voiceclient:

        fname: str = get_audio(src, OUT_PATH, *args)

        if fname:

            audio = discord.FFmpegOpusAudio(fname, codec='copy')

            if voiceclient.is_playing():

                queue.insert(0, QueueEntry(ctx.author, audio, fname))

                await ctx.send(f'Added to queue (Position {len(queue)})')

            else:

                now_playing = QueueEntry(ctx.author, audio, fname)
                voiceclient.play(audio, after=play_next)

                await ctx.send('Now Playing!')
    
    else:

        await ctx.send("musicman can't get in...")


@bot.command(name='disconnect')
async def disconnect(ctx: commands.Context, *args):

    global voiceclient
    global queue
    global now_playing

    if voiceclient:

        if voiceclient.is_playing():

            now_playing = None
            voiceclient.stop()

        await ctx.send(f'Disconnected from {voiceclient.channel.name}')

        await voiceclient.disconnect()
        voiceclient = None


@bot.command(name='ping')
async def ping(ctx: commands.Context, *args):

    now = dt.utcnow()

    await ctx.send(f'Ping took {(now - ctx.message.created_at).total_seconds() * 1000} ms')


@bot.command(name='skip')
async def skip(ctx: commands.Context, *args):

    global voiceclient
    global queue

    if voiceclient and voiceclient.is_playing():
        voiceclient.stop()
        play_next(None)
        await ctx.send('Skipped')

    else:
        await ctx.send('Nothing playing to skip')


@bot.command(name='seek')
async def seek(ctx: commands.Context, timestamp: str, *args):

    global voiceclient
    global now_playing

    if voiceclient and voiceclient.is_playing():

        try:
            td_ts = int(timeparse(timestamp))
            audio = FFmpegOpusAudio(now_playing.fname, codec='copy', before_options=f'-ss {td_ts}')
            queue.append(QueueEntry(now_playing.author, audio, now_playing.fname))
            voiceclient.stop()

            play_next(None)

            await ctx.send(f'Seeked to {timestamp}')

        except Exception:
            await ctx.send(f'Invalid timestamp "{timestamp}"')
    else:
        await ctx.send('No audio playing, nothing to seek')


@bot.command(name='remove')
async def remove(ctx: commands.Context, idx: int, *args):

    global queue

    if len(queue) > 0:
        if idx:
            try:
                queue.remove(queue[idx])
            except Exception:
                await ctx.send(f'Invalid index {idx}')
        else:
            await ctx.send('No index provided to remove')
    else:
        await ctx.send('Nothing to remove, queue is empty')


@bot.command(name='donate')
async def donate(ctx: commands.Context, *args):
    await ctx.send('Donation rejected due to insufficient funds.')


@bot.command(name='join')
async def join(ctx: commands.Context, *args):
    await connect(ctx, *args)


@bot.command(name='pause')
async def pause(ctx: commands.Context, *args):

    global voiceclient

    if voiceclient and voiceclient.is_playing():
        voiceclient.pause()

        await ctx.send('Paused')

    else:

        await ctx.send('Nothing to pause, queue up another song!')


@bot.command(name='resume')
async def resume(ctx: commands.Context, *args):

    global voiceclient

    if voiceclient and voiceclient.is_paused():
        voiceclient.resume()

        await ctx.send('Resumed')

    else:

        await ctx.send('Nothing to resume, queue up another song!')


@bot.command(name='move')
async def move(ctx: commands.Context, start_idx: int, end_idx: int, *args):

    global queue

    if len(queue) > 0:
        if not end_idx:
            end_idx = 0

        if start_idx:

            try:
                qe = queue[start_idx]
                queue.remove(qe)
                queue.insert(end_idx, qe)
                await ctx.send(f'Queue index {start_idx} moved to {end_idx}')
            except Exception:
                await ctx.send('Invalid start or end index provided')
        
        else:

            await ctx.send('No start index provided')
    else:
        await ctx.send('Queue is empty, nothing to move')


# command_map = {
#     'play': play,
#     'disconnect': None,
#     'np': None,
#     'aliases': None,
#     'ping': None,
#     'skip': None,
#     'seek': None,
#     'SoundCloud': None,
#     'remove': None,
#     'loopqueue': None,
#     'search': None,
#     'stats': None,
#     'loop': None,
#     'join': connect,
#     'lyrics': None,
#     'info': None,
#     'resume': None,
#     'settings': None,
#     'move': None,
#     'forward': None,
#     'skipto': None,
#     'clear': None,
#     'replay': None,
#     'clean': None,
#     'pause': None,
#     'removedupes': None,
#     'volume': None,
#     'rewind': None,
#     'playtop': None,
#     'playskip': None,
#     'invite': None,
#     'shuffle': None,
#     'queue': None,
#     'leavecleanup': None,
#     'africa': africa,
# }


@bot.command(name='africa')   
async def africa(ctx: commands.Context, *args):

    await play(ctx, 'africa')

    await ctx.send(';)')


@bot.command(name='ross')   
async def ross(ctx: commands.Context, *args):

    await play(ctx, '"BUSHES OF LOVE" -- Extended Lyric Video')

    await ctx.send('For daddy Ross <3')

bot.run(TOKEN)