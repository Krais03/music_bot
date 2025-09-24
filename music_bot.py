import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
import os

# Konfiguracja intencji
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

# Inicjalizacja bota z prefiksem '!'
bot = commands.Bot(command_prefix='!', intents=intents)

# Kolejka piosenek (słownik na serwery)
queues = {}
voice_clients = {}



# Opcje dla yt-dlp
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


async def play_next(guild_id):
    if guild_id in queues and queues[guild_id]:
        player = queues[guild_id].pop(0)
        voice_clients[guild_id].play(player,
                                     after=lambda e: asyncio.run_coroutine_threadsafe(play_next(guild_id), bot.loop))
        await bot.get_channel(voice_clients[guild_id].channel.id).send(f'Odtwarzam: {player.title}')
    else:
        await asyncio.sleep(300)  # 300 sekund = 5 minut
        # Sprawdź ponownie, czy kolejka jest nadal pusta i czy nic nie jest odtwarzane
        if guild_id in queues and not queues[guild_id] and not voice_clients[guild_id].is_playing():
            await voice_clients[guild_id].disconnect()
            del voice_clients[guild_id]


@bot.event
async def on_ready():
    print(f'Bot zalogowany jako {bot.user}')


@bot.command(name='play', help='Odtwarza piosenkę z YouTube')
async def play(ctx, *, url):
    if not ctx.message.author.voice:
        await ctx.send("Nie jesteś na kanale głosowym!")
        return

    channel = ctx.message.author.voice.channel
    guild_id = ctx.guild.id

    if guild_id not in voice_clients:
        voice_clients[guild_id] = await channel.connect(self_deaf=True)

    async with ctx.typing():
        player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
        if guild_id not in queues:
            queues[guild_id] = []

        if voice_clients[guild_id].is_playing():
            queues[guild_id].append(player)
            await ctx.send(f'Dodano do kolejki: {player.title}')
        else:
            voice_clients[guild_id].play(player, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(guild_id),
                                                                                                  bot.loop))
            await ctx.send(f'Odtwarzam: {player.title}')


@bot.command(name='skip', help='Pomija bieżącą piosenkę')
async def skip(ctx):
    guild_id = ctx.guild.id
    if guild_id in voice_clients and voice_clients[guild_id].is_playing():
        voice_clients[guild_id].stop()
        await ctx.send('Piosenka pominięta!')


@bot.command(name='stop', help='Zatrzymuje odtwarzanie i czyści kolejkę')
async def stop(ctx):
    guild_id = ctx.guild.id
    if guild_id in voice_clients:
        voice_clients[guild_id].stop()
        queues[guild_id] = []
        await ctx.send('Odtwarzanie zatrzymane, kolejka wyczyszczona.')


@bot.command(name='leave', help='Opuszcza kanał głosowy')
async def leave(ctx):
    guild_id = ctx.guild.id
    if guild_id in voice_clients:
        await voice_clients[guild_id].disconnect()
        del voice_clients[guild_id]
        await ctx.send('Bot opuścił kanał.')

TOKEN = os.getenv('DISCORD_TOKEN')
bot.run(TOKEN)
