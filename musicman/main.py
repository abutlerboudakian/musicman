import os
import random
import discord
from discord.ext import commands
from dotenv import load_dotenv
from pytimeparse.timeparse import timeparse
from musicman.util import (
    LoopState, QueueEntry, MusicState,
    get_audio, apply_context, ffmpeg_options
)


load_dotenv()

# Constants
TOKEN = os.getenv('ACCESS_TOKEN')
YDL_OPTIONS = {
    'format': 'bestaudio', 'noplaylist': 'True',
    'username': os.getenv('YT_USERNAME'), 'password': os.getenv('YT_PASSWORD'),
    'cookieFile': f'{os.getenv("TMP_AUDIO_PATH")}youtube.com_cookies.txt'
}


# Globals
bot = commands.Bot(
    command_prefix='!',
    help_command=commands.DefaultHelpCommand(no_category='Commands')
)
guild_map: dict[int, MusicState] = {}


def get_ms(guild_id: int):
    global guild_map
    if guild_id not in guild_map:
        guild_map[guild_id] = MusicState(guild_id)
    return guild_map[guild_id]


def play_next(ctx: commands.Context, error):
    ms: MusicState = get_ms(ctx.guild.id)

    print(error)

    if ms.ls != LoopState.NOW_PLAYING:
        if len(ms.queue) > 0:
            if ms.ls == LoopState.QUEUE:
                ms.queue.append(ms.now_playing)
            ms.now_playing = ms.queue.pop(0)
            ms.voiceclient.play(
                ms.now_playing.audio, after=apply_context(play_next, ctx)
            )
        else:
            ms.now_playing = None
    else:
        audio = discord.FFmpegOpusAudio(ms.now_playing.url, **ffmpeg_options())
        ms.now_playing.audio = audio
        ms.voiceclient.play(
            ms.now_playing.audio, after=apply_context(play_next, ctx)
        )


async def play_either(ctx: commands.Context, top: bool, src: str, *args):

    global YDL_OPTIONS

    ms: MusicState = get_ms(ctx.guild.id)
    CRLF = '\n'
    if not ms.voiceclient:
        await connect(ctx, *args)
    if ms.voiceclient:
        resp: dict = get_audio(YDL_OPTIONS, src, *args)
        if resp:
            url = resp['formats'][0]['url']
            audio = discord.FFmpegOpusAudio(url, **ffmpeg_options())
            if ms.voiceclient.is_playing() or ms.voiceclient.is_paused():
                if top:
                    ms.queue.insert(
                        0, QueueEntry(ctx.author, url, audio, resp['title'])
                    )
                else:
                    ms.queue.append(
                        QueueEntry(ctx.author, url, audio, resp['title'])
                    )
                await ctx.send(
                    f'Added "{resp["title"]}" to queue (Position '
                    f'{"1" if top else len(ms.queue)}).{CRLF}'
                    f'Link: {resp["webpage_url"]}'
                )
            else:
                ms.now_playing = QueueEntry(
                    ctx.author, url, audio, resp['title']
                )
                ms.voiceclient.play(audio, after=apply_context(play_next, ctx))
                await ctx.send(
                    f'Now Playing "{resp["title"]}"!{CRLF}'
                    f'Link: {resp["webpage_url"]}'
                )
        else:
            await ctx.send('No song found that matches keywords...')
    else:
        await ctx.send("musicman can't get in...")


# Main Commands
@bot.command(
    name='connect', help='Summons the bot to your voice channel.',
    aliases=('join',)
)
async def connect(ctx: commands.Context, *args):
    ms: MusicState = get_ms(ctx.guild.id)
    channel: discord.VoiceChannel = ctx.author.voice.channel
    if channel:
        ms.voiceclient = await channel.connect()
        await ctx.send(f'musicman connected to {channel.name}')
    else:
        await ctx.send(f'{ctx.author.name} is not in a voice channel')


@bot.command(name='play', help='Plays a song with the given name or URL.')
async def play(ctx: commands.Context, src: str, *args):
    await play_either(ctx, False, src, *args)


@bot.command(
    name='disconnect',
    help='Disconnect the bot from the voice channel it is in.',
    aliases=('leave',)
)
async def disconnect(ctx: commands.Context, *args):
    ms: MusicState = get_ms(ctx.guild.id)

    for vc in bot.voice_clients:
        if vc.guild.id == ctx.guild.id:
            await vc.disconnect()
            vc.cleanup()

    ms.queue.clear()
    if ms.voiceclient:
        if ms.voiceclient.is_playing() or ms.voiceclient.is_paused():
            ms.ls = LoopState.OFF
            ms.voiceclient.stop()
        await ctx.send(f'Disconnected from {ms.voiceclient.channel.name}')
        await ms.voiceclient.disconnect()
        ms.voiceclient.cleanup()
        ms.voiceclient = None


@bot.command(
    name='np',
    help='Shows what song the bot is currently playing.',
    aliases=('nowplaying',)
)
async def np(ctx: commands.Context, *args):
    ms: MusicState = get_ms(ctx.guild.id)
    if ms.now_playing:
        await ctx.send(f'Currently Playing: {ms.now_playing.title}')
    else:
        await ctx.send('Nothing currently playing, queue up a track!')


@bot.command(name='ping', help='Checks the bot’s response time to Discord.')
async def ping(ctx: commands.Context, *args):
    await ctx.send(f'Ping took {int(bot.latency*1000)} ms')


@bot.command(name='skip', help='Skips the currently playing song.')
async def skip(ctx: commands.Context, *args):
    ms: MusicState = get_ms(ctx.guild.id)
    if ms.voiceclient:
        ms.voiceclient.stop()
        await ctx.send('Skipped')
    else:
        await ctx.send('Nothing playing to skip')


@bot.command(
    name='seek', help='Seeks to a certain point in the current track.'
)
async def seek(ctx: commands.Context, timestamp: str, *args):
    ms: MusicState = get_ms(ctx.guild.id)
    if ms.voiceclient.is_playing() or ms.voiceclient.is_paused():
        try:
            td_ts = int(timeparse(timestamp))
            audio = discord.FFmpegPCMAudio(
                ms.now_playing.url, **ffmpeg_options(td_ts)
            )
            ms.queue.insert(
                0, QueueEntry(
                    ms.now_playing.author, ms.now_playing.url, audio,
                    ms.now_playing.title
                )
            )
            ms.voiceclient.stop()
            await ctx.send(f'Seeked to {timestamp}')
        except Exception:
            await ctx.send(f'Invalid timestamp "{timestamp}"')
    else:
        await ctx.send('No audio playing, nothing to seek')


@bot.command(name='remove', help='Removes a certain entry from the queue.')
async def remove(ctx: commands.Context, idx: int, *args):
    ms: MusicState = get_ms(ctx.guild.id)
    if len(ms.queue) > 0:
        if idx:
            try:
                removed = ms.queue[idx-1]
                ms.queue.remove(ms.queue[idx-1])
                await ctx.send(f'Removed "{removed.title}" at position {idx}')
            except Exception:
                await ctx.send(f'Invalid index {idx}')
        else:
            await ctx.send('No index provided to remove')
    else:
        await ctx.send('Nothing to remove, queue is empty')


@bot.command(name='loopqueue', help='Loops the whole queue.')
async def loopqueue(ctx: commands.Context, *args):
    ms: MusicState = get_ms(ctx.guild.id)
    ms.ls = LoopState.QUEUE
    await ctx.send('Queue loop enabled')


@bot.command(name='loop', help='Loop the currently playing song.')
async def loop(ctx: commands.Context, *args):
    ms: MusicState = get_ms(ctx.guild.id)

    if ms.now_playing:
        ms.ls = LoopState.NOW_PLAYING
        await ctx.send(f'"{ms.now_playing.title}" loop enabled')
    else:
        await ctx.send('Nothing playing to loop')


@bot.command(name='noloop', help='Stop looping')
async def noloop(ctx: commands.Context, *args):
    ms: MusicState = get_ms(ctx.guild.id)

    ms.ls = LoopState.OFF
    await ctx.send('Looping disabled')


@bot.command(name='donate', help='Don\'t actually give me money please')
async def donate(ctx: commands.Context, *args):
    await ctx.send('Donation rejected due to insufficient funds.')


@bot.command(name='pause', help='Pauses the currently playing track')
async def pause(ctx: commands.Context, *args):
    ms: MusicState = get_ms(ctx.guild.id)
    if ms.voiceclient and ms.voiceclient.is_playing():
        ms.voiceclient.pause()
        await ctx.send(f'Paused "{ms.now_playing.title}"')
    else:
        await ctx.send('Nothing to pause, queue up another song!')


@bot.command(name='resume', help='Resume paused music')
async def resume(ctx: commands.Context, *args):
    ms: MusicState = get_ms(ctx.guild.id)
    if ms.voiceclient and ms.voiceclient.is_paused():
        ms.voiceclient.resume()
        await ctx.send(f'Resumed "{ms.now_playing.title}"')
    else:
        await ctx.send('Nothing to resume, queue up another song!')


@bot.command(
    name='move',
    help=(
        'Moves a certain song to the first position in the queue or to '
        'a chosen position'
    )
)
async def move(ctx: commands.Context, start_idx: int, end_idx: int, *args):
    ms: MusicState = get_ms(ctx.guild.id)
    if len(ms.queue) > 0:
        if not end_idx:
            end_idx = 1
        if start_idx:
            try:
                qe = ms.queue[start_idx-1]
                ms.queue.remove(qe)
                ms.queue.insert(end_idx-1, qe)
                await ctx.send(
                    f'"{qe.title}" moved from {start_idx} to {end_idx}'
                )
            except Exception:
                await ctx.send('Invalid start or end index provided')

        else:
            await ctx.send('No start index provided')
    else:
        await ctx.send('Queue is empty, nothing to move')


@bot.command(name='skipto', help='Skips to a certain position in the queue.')
async def skipto(ctx: commands.Context, idx: int, *args):
    ms: MusicState = get_ms(ctx.guild.id)
    try:
        qe = ms.queue[idx-1]
        while ms.now_playing != qe:
            await skip(ctx)
        await ctx.send(
            f'Skipped to "{ms.now_playing.title}" at position {idx}'
        )
    except Exception:
        await ctx.send(f'Invalid index {idx}')


@bot.command(name='clear', help='Clears the queue.')
async def clear(ctx: commands.Context, *args):
    ms: MusicState = get_ms(ctx.guild.id)
    ms.queue.clear()
    await ctx.send('Cleared queue')


@bot.command(name='replay', help='Reset the progress of the current song')
async def replay(ctx: commands.Context, *args):
    await seek(ctx, '00:00', *args)


@bot.command(name='clean', help='Deletes the bot’s messages and commands.')
async def clean(ctx: commands.Context, *args):
    msg: discord.Message = ctx.message
    channel: discord.TextChannel = msg.channel
    await channel.purge(limit=1000, check=lambda m: m.author.id == bot.user.id)
    await ctx.send('Removed all messages sent by musicman!')


@bot.command(
    name='removedupes', help='Removes duplicate songs from the queue.'
)
async def removedupes(ctx: commands.Context, *args):
    ms: MusicState = get_ms(ctx.guild.id)
    urls = set()
    n_queue = []
    for q in ms.queue:
        if q.url not in urls:
            urls.add(q.url)
            n_queue.append(q)
    ms.queue = n_queue
    await ctx.send('Duplicates removed')


@bot.command(
    name='playtop', help='Like the play command, but queues from the top.'
)
async def playtop(ctx: commands.Context, src: str, *args):
    await play_either(ctx, True, src, *args)


@bot.command(
    name='playskip',
    help='Adds a song to the top of the queue then skips to it.'
)
async def playskip(ctx: commands.Context, src: str, *args):
    ms: MusicState = get_ms(ctx.guild.id)
    await playtop(ctx, src, *args)
    if len(ms.queue) > 0:
        await skip(ctx, *args)


@bot.command(name='shuffle', help='Shuffles the queue.')
async def shuffle(ctx: commands.Context, *args):
    ms: MusicState = get_ms(ctx.guild.id)
    random.shuffle(ms.queue)
    await ctx.send('Queue shuffled')


@bot.command(name='queue', help='View the queue.')
async def view_queue(ctx: commands.Context, *args):
    ms: MusicState = get_ms(ctx.guild.id)
    if len(ms.queue) > 0:
        embed = discord.Embed()
        embed.title = 'Queue'
        for i in range(len(ms.queue)):
            embed.add_field(
                name=f'Position {i+1}', value=ms.queue[i].title, inline=False
            )
        await ctx.send(embed=embed)
    else:
        await ctx.send('Queue empty')


@bot.command(
    name='leavecleanup', help='Removes absent user’s songs from the Queue.'
)
async def leavecleanup(ctx: commands.Context, *args):
    ms: MusicState = get_ms(ctx.guild.id)

    if ms.voiceclient:
        channel: discord.VoiceChannel = ms.voiceclient.channel
        members: list[int] = [m.id for m in channel.members]

        ms.queue = [q for q in ms.queue if q.author.id in members]

        if ms.now_playing.author.id not in members:
            await skip(ctx, *args)

        await ctx.send('Removed all songs submitted by absent users')


# Easter egg commands
@bot.command(name='africa', hidden=True)
async def africa(ctx: commands.Context, *args):
    await play(ctx, 'africa')
    await ctx.send(';)')


@bot.command(name='test', hidden=True)
async def test(ctx: commands.Context, *args):
    await play(ctx, 'hello world')
    await ctx.send('Hello world!')


@bot.command(name='ross', hidden=True)
async def ross(ctx: commands.Context, *args):
    await play(ctx, '"BUSHES OF LOVE" -- Extended Lyric Video')
    await ctx.send('For daddy Ross <3')

bot.run(TOKEN)
