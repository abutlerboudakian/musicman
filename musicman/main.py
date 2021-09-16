import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from musicman.music_utils import get_audio

load_dotenv()
TOKEN = os.getenv('ACCESS_TOKEN')
OUT_PATH = os.getenv('TMP_AUDIO_PATH')

bot = commands.Bot(command_prefix='!')
voiceclient: discord.VoiceClient = None
queue: list[discord.AudioSource] = []

def play_next(error):

    global voiceclient
    global queue

    if len(queue) > 0:

        audio = queue.pop()
        voiceclient.play(audio, after=play_next)

@bot.command(name='connect')
async def connect(ctx: commands.Context, *args):

    global voiceclient

    channel: discord.VoiceChannel = ctx.author.voice.channel

    if channel:
        voiceclient = await channel.connect()

        await ctx.send(f'musicman connected to {channel.name}')

    else:
        await ctx.send(f'{ctx.author.name} is not in a voice channel')


@bot.command(name='play')
async def play(ctx: commands.Context, src: str, *args):

    global voiceclient
    global queue
    global OUT_PATH

    if not voiceclient:
        await connect(ctx, *args)

    if voiceclient:

        fname: str = get_audio(src, OUT_PATH, *args)

        if fname:

            audio = discord.FFmpegOpusAudio(fname)

            if voiceclient.is_playing():

                queue.append(audio)

                await ctx.send(f'Added to queue (Position {len(queue)})')

            else:

                voiceclient.play(audio, after=play_next)

                await ctx.send('Now Playing!')
    
    else:

        await ctx.send("musicman can't get in...")


@bot.command(name='africa')   
async def africa(ctx: commands.Context, *args):

    await play(ctx, 'africa')

    await ctx.send(';)')


@bot.command(name='ross')   
async def ross(ctx: commands.Context, *args):

    await play(ctx, '"BUSHES OF LOVE" -- Extended Lyric Video')

    await ctx.send('For daddy Ross <3')


@bot.command(name='leavecleanup')
async def leavecleanup(ctx: commands.Context, *args):

    global voiceclient
    global queue

    if voiceclient:

        if voiceclient.is_playing():

            voiceclient.stop()

        await voiceclient.disconnect()
        voiceclient = None
        queue = []


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

bot.run(TOKEN)