import discord
from discord.ext import commands
import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import asyncio
import time
import logging

# Configurar a autenticação da API do Spotify com variáveis de ambiente
SPOTIPY_CLIENT_ID = '' #Colocar seu Client ID
SPOTIPY_CLIENT_SECRET = '' #Colocar seu Client Secret

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIPY_CLIENT_ID,
    client_secret=SPOTIPY_CLIENT_SECRET
))

token_bot = '' #colocar o token do seu bot do discord
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Configurar logging
logging.basicConfig(level=logging.INFO)

class MusicBot:
    def __init__(self):
        self.queue = []
        self.loop = False
        self.volume = 0.5  # Volume inicial (50%)

    async def play_next(self, ctx):
        if self.queue:
            track_info = self.queue.pop(0)
            try:
                source = discord.FFmpegPCMAudio(track_info['filename'])
                ctx.voice_client.play(
                    source, after=lambda e: bot.loop.create_task(self.play_next(ctx))
                )
                ctx.voice_client.source = discord.PCMVolumeTransformer(ctx.voice_client.source)
                ctx.voice_client.source.volume = self.volume

                embed = discord.Embed(
                    title="<:spotify:1267216530878238720> Tocando agora", color=discord.Color.green()
                )
                embed.add_field(name="🎶 Música", value=f"[{track_info['track_name']}]({track_info['url']})", inline=False)
                embed.add_field(name="🎤 Artista", value=track_info['track_artists'], inline=False)
                embed.add_field(name="⏱ Duração", value=track_info['track_duration'], inline=False)
                if track_info['track_image_url']:
                    embed.set_thumbnail(url=track_info['track_image_url'])
                await ctx.send(embed=embed)

                if self.loop:
                    self.queue.append(track_info)

                await asyncio.sleep(2)
                self.cleanup_files()

            except Exception as e:
                await ctx.send(f'Erro ao tentar tocar a música: {str(e)}')
            finally:
                self.cleanup_files()

    async def run_spotdl(self, url):
        process = await asyncio.create_subprocess_exec(
            'spotdl', url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise Exception(f'Erro ao executar spotdl: {stderr.decode()}')

    def cleanup_files(self):
        for file in os.listdir('.'):
            if file.endswith('.mp3'):
                attempts = 0
                while attempts < 5:
                    try:
                        os.remove(file)
                        logging.info(f'Arquivo {file} removido com sucesso.')
                        break
                    except PermissionError:
                        attempts += 1
                        logging.warning(f'Não foi possível remover o arquivo {file}. Tentando novamente ({attempts}/5).')
                        time.sleep(1)

music_bot = MusicBot()

@bot.event
async def on_ready():
    logging.info(f'Bot está online como {bot.user}!')
    await bot.change_presence(activity=discord.Game(name="🎶 Tocando músicas!"))

@bot.command(name='play')
async def play(ctx, *, url: str = None):
    try:
        if not ctx.voice_client:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send('Você não está conectado a um canal de voz.')
                return

        if ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send('▶️ Música retomada.')
            return

        if url is None:
            await ctx.send('Por favor, forneça um link da música do Spotify ou do YouTube.')
            return

        if 'spotify.com' in url:
            if 'playlist' in url:
                await ctx.send('Buscando a playlist no Spotify, aguarde...')
                playlist_id = url.split('/')[-1].split('?')[0]
                playlist_tracks = sp.playlist_tracks(playlist_id)

                for item in playlist_tracks['items']:
                    track = item['track']
                    track_url = track['external_urls']['spotify']
                    await music_bot.run_spotdl(track_url)

                    filename = next((file for file in os.listdir('.') if file.endswith('.mp3')), None)
                    if not filename:
                        await ctx.send('Não foi possível encontrar o arquivo baixado.')
                        continue

                    track_name = track['name']
                    track_artists = ', '.join(artist['name'] for artist in track['artists'])
                    track_duration_ms = track['duration_ms']
                    track_duration_min = track_duration_ms // 60000
                    track_duration_sec = (track_duration_ms // 1000) % 60
                    track_image_url = track['album']['images'][0]['url'] if track['album']['images'] else None

                    track_data = {
                        'filename': filename,
                        'url': track_url,
                        'track_name': track_name,
                        'track_artists': track_artists,
                        'track_duration': f"{track_duration_min}:{track_duration_sec:02d}",
                        'track_image_url': track_image_url
                    }
                    music_bot.queue.append(track_data)

                await ctx.send(f'Playlist adicionada à fila com {len(playlist_tracks["items"])} músicas.')

                if not ctx.voice_client.is_playing():
                    await music_bot.play_next(ctx)
            else:
                await ctx.send('Buscando a música no Spotify, aguarde...')
                await music_bot.run_spotdl(url)

                filename = next((file for file in os.listdir('.') if file.endswith('.mp3')), None)
                if not filename:
                    await ctx.send('Não foi possível encontrar o arquivo baixado.')
                    return

                track_info = sp.track(url)
                track_name = track_info['name']
                track_artists = ', '.join(artist['name'] for artist in track_info['artists'])
                track_duration_ms = track_info['duration_ms']
                track_duration_min = track_duration_ms // 60000
                track_duration_sec = (track_duration_ms // 1000) % 60
                track_image_url = track_info['album']['images'][0]['url'] if track_info['album']['images'] else None

                track_data = {
                    'filename': filename,
                    'url': url,
                    'track_name': track_name,
                    'track_artists': track_artists,
                    'track_duration': f"{track_duration_min}:{track_duration_sec:02d}",
                    'track_image_url': track_image_url
                }
                music_bot.queue.append(track_data)

                if not ctx.voice_client.is_playing():
                    await music_bot.play_next(ctx)
                else:
                    position = len(music_bot.queue)
                    embed = discord.Embed(
                        title="Música adicionada à fila", color=discord.Color.blue()
                    )
                    embed.add_field(name="🎶 Música", value=f"[{track_name}]({url})", inline=False)
                    embed.add_field(name="🎤 Artista", value=track_artists, inline=False)
                    embed.add_field(name="⏱ Duração", value=f"{track_duration_min}:{track_duration_sec:02d}", inline=False)
                    embed.add_field(name="📃 Posição na fila", value=position, inline=False)
                    if track_image_url:
                        embed.set_thumbnail(url=track_image_url)
                    await ctx.send(embed=embed)
        else:
            await ctx.send('Link inválido. Por favor, forneça um link válido do Spotify.')
    except Exception as e:
        await ctx.send(f'Erro ao tentar adicionar a música à fila: {str(e)}')

@bot.command(name='volume')
async def volume_command(ctx, volume_level: int):
    try:
        if ctx.voice_client is None:
            await ctx.send('Não estou conectado a um canal de voz.')
            return

        if 0 <= volume_level <= 100:
            music_bot.volume = volume_level / 100
            ctx.voice_client.source.volume = music_bot.volume
            await ctx.send(f'🔊 Volume ajustado para {volume_level}%')
        else:
            await ctx.send('Por favor, forneça um valor de volume entre 0 e 100.')
    except Exception as e:
        await ctx.send(f'Erro ao tentar ajustar o volume: {str(e)}')

@bot.command(name='queue')
async def queue_command(ctx):
    try:
        if not music_bot.queue:
            await ctx.send('A fila está vazia.')
        else:
            embed = discord.Embed(title="Fila de Músicas", color=discord.Color.purple())
            for i, track in enumerate(music_bot.queue):
                embed.add_field(name=f"{i+1}. {track['track_name']}", value=f"Artista: {track['track_artists']}\nDuração: {track['track_duration']}", inline=False)
            await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f'Erro ao tentar exibir a fila: {str(e)}')

@bot.command(name='remove')
async def remove_command(ctx, index: int):
    try:
        if index < 1 or index > len(music_bot.queue):
            await ctx.send('Índice inválido.')
        else:
            removed_track = music_bot.queue.pop(index-1)
            await ctx.send(f'Removido: {removed_track["track_name"]} da fila.')
    except Exception as e:
        await ctx.send(f'Erro ao tentar remover a música da fila: {str(e)}')

@bot.command(name='clear')
async def clear_command(ctx):
    try:
        music_bot.queue.clear()
        await ctx.send('A fila foi limpa.')
    except Exception as e:
        await ctx.send(f'Erro ao tentar limpar a fila: {str(e)}')

@bot.command(name='loop')
async def loop_command(ctx):
    try:
        music_bot.loop = not music_bot.loop
        await ctx.send('🔁 Loop ' + ('ativado' if music_bot.loop else 'desativado') + '.')
    except Exception as e:
        await ctx.send(f'Erro ao tentar ativar/desativar o loop: {str(e)}')

@bot.command(name='join')
async def join_command(ctx):
    try:
        if not ctx.author.voice:
            await ctx.send('Você não está conectado a um canal de voz.')
            return

        if ctx.voice_client:
            await ctx.voice_client.move_to(ctx.author.voice.channel)
        else:
            await ctx.author.voice.channel.connect()
    except Exception as e:
        await ctx.send(f'Erro ao tentar entrar no canal de voz: {str(e)}')

@bot.command(name='pause')
async def pause_command(ctx):
    try:
        if ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send('⏸ Música pausada.')
        else:
            await ctx.send('Não estou tocando nenhuma música no momento.')
    except Exception as e:
        await ctx.send(f'Erro ao tentar pausar a música: {str(e)}')

@bot.command(name='ajuda')
async def ajuda_command(ctx):
    embed = discord.Embed(title="Comandos de Ajuda", color=discord.Color.blue())
    embed.add_field(name="!play [link]", value="Toca uma música ou playlist do Spotify.", inline=False)
    embed.add_field(name="!volume [0-100]", value="Ajusta o volume do bot.", inline=False)
    embed.add_field(name="!queue", value="Mostra a fila de músicas.", inline=False)
    embed.add_field(name="!remove [número]", value="Remove a música da posição 'número' da fila.", inline=False)
    embed.add_field(name="!clear", value="Limpa a fila de músicas.", inline=False)
    embed.add_field(name="!loop", value="Ativa/desativa o loop da fila.", inline=False)
    embed.add_field(name="!join", value="Faz o bot entrar no canal de voz.", inline=False)
    embed.add_field(name="!pause", value="Pausa a música atual.", inline=False)
    embed.add_field(name="!skip", value="Pula para a próxima música.", inline=False)
    embed.add_field(name="!leave", value="Faz o bot sair do canal de voz.", inline=False)
    embed.add_field(name="!stop", value="Para a música atual.", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='skip')
async def skip_command(ctx):
    try:
        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send('⏭ Música pulada.')
        else:
            await ctx.send('Não estou tocando nenhuma música no momento.')
    except Exception as e:
        await ctx.send(f'Erro ao tentar pular a música: {str(e)}')

@bot.command(name='leave')
async def leave_command(ctx):
    try:
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send('👋 Desconectado do canal de voz.')
        else:
            await ctx.send('Não estou conectado a nenhum canal de voz.')
    except Exception as e:
        await ctx.send(f'Erro ao tentar sair do canal de voz: {str(e)}')

@bot.command(name='stop')
async def stop_command(ctx):
    try:
        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            music_bot.queue.clear()
            await ctx.send('⏹ Música parada e fila limpa.')
        else:
            await ctx.send('Não estou tocando nenhuma música no momento.')
    except Exception as e:
        await ctx.send(f'Erro ao tentar parar a música: {str(e)}')

bot.run(token_bot)
