from datetime import timedelta as td
import os
import re
import discord
from discord.ext import commands
from dotenv import load_dotenv
import lavalink
from lavalink.models import AudioTrack
from pytimeparse.timeparse import timeparse
from musicman.util import handle_spotify


load_dotenv()


# Constants
BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = commands.Bot(
    command_prefix='!',
    help_command=commands.DefaultHelpCommand(no_category='Commands')
)


@bot.event
async def on_ready():
    bot.lavalink = lavalink.Client(bot.user.id)
    bot.lavalink.add_node(
        'localhost', 2333, os.getenv('LAVALINK_PASSWORD'), 'us',
        name='default-node'
    )

    lavalink.add_event_hook(track_hook)


async def track_hook(event):
    if isinstance(event, lavalink.events.QueueEndEvent):
        # When this track_hook receives a "QueueEndEvent" from lavalink.py
        # it indicates that there are no tracks left in the player's queue.
        # To save on resources, we can tell the bot to disconnect from the
        #   voicechannel.
        guild_id = int(event.player.guild_id)
        guild = bot.get_guild(guild_id)
        await guild.voice_client.disconnect(force=True)


url_rx = re.compile(r'https?://(?:www\.)?.+')


class LavalinkVoiceClient(discord.VoiceClient):
    """
    This is the preferred way to handle external voice sending
    This client will be created via a cls in the connect method of the channel
    see the following documentation:
    https://discordpy.readthedocs.io/en/latest/api.html#voiceprotocol
    """

    def __init__(
        self, client: discord.Client, channel: discord.abc.Connectable
    ):
        self.client = client
        self.channel = channel
        # ensure there exists a client already
        if hasattr(self.client, 'lavalink'):
            self.lavalink = self.client.lavalink
        else:
            self.client.lavalink = lavalink.Client(client.user.id)
            self.client.lavalink.add_node(
                    'localhost',
                    2333,
                    os.getenv('LAVALINK_PASSWORD'),
                    'us',
                    name='default-node')
            self.lavalink = self.client.lavalink

    async def on_voice_server_update(self, data):
        # the data needs to be transformed before being handed down to
        # voice_update_handler
        lavalink_data = {
                't': 'VOICE_SERVER_UPDATE',
                'd': data
                }
        await self.lavalink.voice_update_handler(lavalink_data)

    async def on_voice_state_update(self, data):
        # the data needs to be transformed before being handed down to
        # voice_update_handler
        lavalink_data = {
                't': 'VOICE_STATE_UPDATE',
                'd': data
                }
        await self.lavalink.voice_update_handler(lavalink_data)

    async def connect(self, *, timeout: float, reconnect: bool) -> None:
        """
        Connect the bot to the voice channel and create a player_manager
        if it doesn't exist yet.
        """
        # ensure there is a player_manager when creating a new voice_client
        self.lavalink.player_manager.create(guild_id=self.channel.guild.id)
        await self.channel.guild.change_voice_state(channel=self.channel)

    async def disconnect(self, *, force: bool) -> None:
        """
        Handles the disconnect.
        Cleans up running player and leaves the voice client.
        """
        player = self.lavalink.player_manager.get(self.channel.guild.id)

        # no need to disconnect if we are not connected
        if not force and not player.is_connected:
            return

        # None means disconnect
        await self.channel.guild.change_voice_state(channel=None)

        # update the channel_id of the player to None
        # this must be done because the on_voice_state_update that
        # would set channel_id to None doesn't get dispatched after the
        # disconnect
        player.channel_id = None
        self.cleanup()


async def play_either(ctx: commands.Context, top: bool, src: str, *args):

    SP_CLIENT = os.getenv('SP_CLIENT')
    SP_SECRET = os.getenv('SP_SECRET')

    if 'open.spotify.com' in [s.lower() for s in src.split('/')]:
        src = handle_spotify(SP_CLIENT, SP_SECRET, src)
        if isinstance(src, list):
            return await ctx.send(
                'Use the !playlist command to queue playlists'
            )
    else:
        src = ' '.join([src, *args])
    player: lavalink.DefaultPlayer = bot.lavalink.player_manager.get(
        ctx.guild.id
    )

    src = src.strip('<>')

    if not url_rx.match(src):
        src = f'ytsearch:{src}'

    results = await player.node.get_tracks(src)

    if not (results and results['tracks']):
        return await ctx.send(f'No results found for "{src}"')

    embed = discord.Embed(color=discord.Color.blurple())

    if results['loadType'] == 'PLAYLIST_LOADED':
        return await ctx.send('Use the !playlist command to queue playlists')
    else:
        track = results['tracks'][0]
        embed.title = 'Track Enqueued'
        embed.description = (
            f'[{track["info"]["title"]}]({track["info"]["uri"]})'
        )

        # You can attach additional information to audiotracks through kwargs,
        # however this involves constructing the AudioTrack class yourself.
        track = lavalink.models.AudioTrack(
            track, ctx.author.id, recommended=True
        )
        player.add(requester=ctx.author.id, track=track)

    await ctx.send(embed=embed)

    if not player.is_playing:
        await player.play()


# Main Commands
@bot.command(
    name='connect', help='Summons the bot to your voice channel.',
    aliases=('join',)
)
async def connect(ctx: commands.Context, *args):

    # ms: MusicState = get_ms(ctx.guild.id)
    channel: discord.VoiceChannel = ctx.author.voice.channel
    if channel:
        await ctx.author.voice.channel.connect(cls=LavalinkVoiceClient)
        await ctx.send(f'musicman connected to {channel.name}')
    else:
        await ctx.send(f'{ctx.author.name} is not in a voice channel')


@bot.command(
    name='play', help='Plays a song with the given name or URL.',
    aliases=('p',)
)
async def play(ctx: commands.Context, src: str, *args):
    await play_either(ctx, False, src, *args)


@bot.command(
    name='playlist',
    help='Loads a playlist into the queue with a given name or URL.',
    aliases=('pl',)
)
async def playlist(ctx: commands.Context, src: str, *args):

    SP_CLIENT = os.getenv('SP_CLIENT')
    SP_SECRET = os.getenv('SP_SECRET')

    player: lavalink.DefaultPlayer = bot.lavalink.player_manager.get(
        ctx.guild.id
    )

    if player.is_connected:

        await ctx.send(f'Attempting to add {src}')

        tracks = []

        embed = discord.Embed(color=discord.Color.blurple())
        embed.title = 'Playlist Enqueued!'

        if 'open.spotify.com' in [s.lower() for s in src.split('/')]:
            sp_tracks = handle_spotify(SP_CLIENT, SP_SECRET, src)

            for track in sp_tracks:
                result = await player.node.get_tracks(track)
                tracks.append(result['tracks'][0])

            embed.description = f'{src} - {len(tracks)} tracks'
        else:
            src = ' '.join(src, *args)

            src = src.strip('<>')

            if not url_rx.match(src):
                src = f'ytsearch:{src}'

            results = await player.node.get_tracks(src)

            if not (
                results and results['tracks'] and
                results['loadType'] == 'PLAYLIST_LOADED'
            ):
                return await ctx.send(f'No results found for "{src}"')

            embed.description = (
                f'{results["playlistInfo"]["name"]} - {len(tracks)} tracks'
            )

            tracks = results['tracks']

        for track in tracks:
            player.add(requester=ctx.author.id, track=track)

        await ctx.send(embed=embed)

        if not player.is_playing:
            await player.play()

    else:
        await ctx.send("musicman must be in a channel first")


@bot.command(
    name='disconnect',
    help='Disconnect the bot from the voice channel it is in.',
    aliases=('leave',)
)
async def disconnect(ctx: commands.Context, *args):
    player = bot.lavalink.player_manager.get(ctx.guild.id)

    if not player.is_connected:
        # We can't disconnect, if we're not connected.
        return await ctx.send('Not connected.')

    if not ctx.author.voice or (
        player.is_connected and
        ctx.author.voice.channel.id != int(player.channel_id)
    ):
        # Abuse prevention. Users not in voice channels, or not in the same
        # voice channel as the bot may not disconnect the bot.
        return await ctx.send('You\'re not in my voicechannel!')

    # Clear the queue to ensure old tracks don't start playing
    # when someone else queues something.
    player.queue.clear()
    # Stop the current track so Lavalink consumes less resources.
    await player.stop()
    # Disconnect from the voice channel.
    await ctx.voice_client.disconnect(force=True)
    await ctx.send('*⃣ | Disconnected.')


@bot.command(
    name='np',
    help='Shows what song the bot is currently playing.',
    aliases=('nowplaying',)
)
async def np(ctx: commands.Context, *args):

    player: lavalink.DefaultPlayer = bot.lavalink.player_manager.get(
        ctx.guild.id
    )

    current_duration = td(milliseconds=player.position_timestamp)

    if player.is_playing:
        current: lavalink.AudioTrack = player.current
        await ctx.send(
            f'Currently Playing: {current.title} '
            f'at {current_duration.total_seconds() // 3600}:'
            f'{current_duration.total_seconds() // 60}:'
            f'{int(current_duration.total_seconds()) % 60}'
        )
    else:
        await ctx.send('Nothing currently playing, queue up a track!')


@bot.command(name='ping', help='Checks the bot’s response time to Discord.')
async def ping(ctx: commands.Context, *args):
    await ctx.send(f'Ping took {int(bot.latency*1000)} ms')


@bot.command(name='skip', help='Skips the currently playing song.')
async def skip(ctx: commands.Context, *args):
    player: lavalink.DefaultPlayer = bot.lavalink.player_manager.get(
        ctx.guild.id
    )
    if player.is_playing:
        await player.skip()
        await ctx.send('Skipped')
    else:
        await ctx.send('Nothing playing to skip')


@bot.command(
    name='seek', help='Seeks to a certain point in the current track.'
)
async def seek(ctx: commands.Context, timestamp: str, *args):
    player: lavalink.DefaultPlayer = bot.lavalink.player_manager.get(
        ctx.guild.id
    )
    if player.is_playing:
        try:
            td_ts = int(timeparse(timestamp)) * 1000
            await player.seek(td_ts)
            await ctx.send(f'Seeked to {timestamp}')
        except Exception:
            await ctx.send(f'Invalid timestamp "{timestamp}"')
    else:
        await ctx.send('No audio playing, nothing to seek')


@bot.command(name='remove', help='Removes a certain entry from the queue.')
async def remove(ctx: commands.Context, idx: int, *args):
    player: lavalink.DefaultPlayer = bot.lavalink.player_manager.get(
        ctx.guild.id
    )

    if len(player.queue) > 0:
        if idx:
            try:
                removed: lavalink.AudioTrack = player.queue[idx]
                player.queue = [
                    q for (i, q) in enumerate(player.queue) if i != idx-1
                ]
                await ctx.send(f'Removed "{removed.title}" at position {idx}')
            except Exception:
                await ctx.send(f'Invalid index {idx}')
        else:
            await ctx.send('No index provided to remove')
    else:
        await ctx.send('Nothing to remove, queue is empty')


# @bot.command(name='loopqueue', help='Loops the whole queue.')
# async def loopqueue(ctx: commands.Context, *args):
#     ms: MusicState = get_ms(ctx.guild.id)
#     ms.ls = LoopState.QUEUE
#     await ctx.send('Queue loop enabled')


@bot.command(name='loop', help='Loop the currently playing song.')
async def loop(ctx: commands.Context, *args):
    player: lavalink.DefaultPlayer = bot.lavalink.player_manager.get(
        ctx.guild.id
    )

    if player.is_playing:
        player.set_repeat(True)
        await ctx.send(f'"{player.current.title}" loop enabled')
    else:
        await ctx.send('Nothing playing to loop')


# @bot.command(
#     name='playloop', help='Playtops the given song and enables loop',
#     aliases=('ploop',)
# )
# async def playloop(ctx: commands.Context, src: str, *args):
#     player: lavalink.DefaultPlayer = bot.lavalink.player_manager.get(
#         ctx.guild.id
#     )
#     player.set_repeat(False)
#     await play(ctx, src, *args)
#     await loop(ctx, *args)


@bot.command(name='noloop', help='Stop looping')
async def noloop(ctx: commands.Context, *args):
    player: lavalink.DefaultPlayer = bot.lavalink.player_manager.get(
        ctx.guild.id
    )
    player.set_repeat(False)
    await ctx.send('Looping disabled')


@bot.command(name='donate', help='Don\'t actually give me money please')
async def donate(ctx: commands.Context, *args):
    await ctx.send('Donation rejected due to insufficient funds.')


@bot.command(name='pause', help='Pauses the currently playing track')
async def pause(ctx: commands.Context, *args):
    player: lavalink.DefaultPlayer = bot.lavalink.player_manager.get(
        ctx.guild.id
    )
    if player.is_playing:
        current: AudioTrack = player.current
        await player.set_pause(True)
        await ctx.send(f'Paused "{current.title}"')
    else:
        await ctx.send('Nothing to pause, queue up another song!')


@bot.command(name='resume', help='Resume paused music')
async def resume(ctx: commands.Context, *args):
    player: lavalink.DefaultPlayer = bot.lavalink.player_manager.get(
        ctx.guild.id
    )
    if player.paused:
        await player.set_pause(False)
        await ctx.send(f'Resumed "{player.current.title}"')
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
    player: lavalink.DefaultPlayer = bot.lavalink.player_manager.get(
        ctx.guild.id
    )
    if len(player.queue) > 0:
        if not end_idx:
            end_idx = 1
        if start_idx:
            try:
                queue = player.queue
                qe = queue[start_idx-1]
                queue.remove(qe)
                queue.insert(end_idx-1, qe)
                player.queue = queue
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
    player: lavalink.DefaultPlayer = bot.lavalink.player_manager.get(
        ctx.guild.id
    )
    try:
        qe = player.queue[idx-1]
        while player.current != qe:
            await skip(ctx)
        await ctx.send(
            f'Skipped to "{player.current.title}" at position {idx}'
        )
    except Exception:
        await ctx.send(f'Invalid index {idx}')


@bot.command(name='clear', help='Clears the queue.')
async def clear(ctx: commands.Context, *args):
    player: lavalink.DefaultPlayer = bot.lavalink.player_manager.get(
        ctx.guild.id
    )
    player.queue.clear()
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


# @bot.command(
#     name='removedupes', help='Removes duplicate songs from the queue.'
# )
# async def removedupes(ctx: commands.Context, *args):
#     ms: MusicState = get_ms(ctx.guild.id)
#     urls = set()
#     n_queue = []
#     for q in ms.queue:
#         if q.url not in urls:
#             urls.add(q.url)
#             n_queue.append(q)
#     ms.queue = n_queue
#     await ctx.send('Duplicates removed')


# @bot.command(
#     name='playtop', help='Like the play command, but queues from the top.'
# )
# async def playtop(ctx: commands.Context, src: str, *args):
#     await play_either(ctx, True, src, *args)


# @bot.command(
#     name='playskip',
#     help='Adds a song to the top of the queue then skips to it.'
# )
# async def playskip(ctx: commands.Context, src: str, *args):
#     ms: MusicState = get_ms(ctx.guild.id)
#     await playtop(ctx, src, *args)
#     if len(ms.queue) > 0:
#         await skip(ctx, *args)


@bot.command(name='shuffle', help='Shuffles the queue.')
async def shuffle(ctx: commands.Context, *args):
    player: lavalink.DefaultPlayer = bot.lavalink.player_manager.get(
        ctx.guild.id
    )
    player.set_shuffle(True)
    await ctx.send('Queue shuffled')


@bot.command(name='noshuffle', help='Disables queue shuffling.')
async def unshuffle(ctx: commands.Context, *args):
    player: lavalink.DefaultPlayer = bot.lavalink.player_manager.get(
        ctx.guild.id
    )
    player.set_shuffle(False)


@bot.command(name='queue', help='View the queue.')
async def view_queue(ctx: commands.Context, *args):
    player: lavalink.DefaultPlayer = bot.lavalink.player_manager.get(
        ctx.guild.id
    )
    if len(player.queue) > 0:
        embed = discord.Embed()
        embed.title = 'Queue'
        for i in range(len(player.queue)):
            embed.add_field(
                name=f'Position {i+1}', value=player.queue[i].title,
                inline=False
            )
        await ctx.send(embed=embed)
    else:
        await ctx.send('Queue empty')


# @bot.command(
#     name='leavecleanup', help='Removes absent user’s songs from the Queue.'
# )
# async def leavecleanup(ctx: commands.Context, *args):
#     ms: MusicState = get_ms(ctx.guild.id)

#     if ms.voiceclient:
#         channel: discord.VoiceChannel = ms.voiceclient.channel
#         members: list[int] = [m.id for m in channel.members]

#         ms.queue = [q for q in ms.queue if q.author.id in members]

#         if ms.now_playing.author.id not in members:
#             await skip(ctx, *args)

#         await ctx.send('Removed all songs submitted by absent users')


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

bot.run(BOT_TOKEN)
