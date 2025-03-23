import asyncio
import discord
import logging
import re
import datetime
from discord.ext import commands, tasks
from ..utils.music_queue import GuildMusicState, Song
from ..utils.youtube_dl import YTDLSource
from ..utils.embed_creator import EmbedCreator

logger = logging.getLogger('music')

class Music(commands.Cog):
    """Music related commands."""

    def __init__(self, bot):
        self.bot = bot
        self.guild_music_state = GuildMusicState(bot)
        self.check_inactivity.start()
        self.song_finished_flags = {}  # Diccionario para rastrear canciones finalizadas
        self.command_channels = {}  # Nuevo diccionario para rastrear los canales de comando
        self.process_finished_songs.start()
    
    def cog_unload(self):
        self.check_inactivity.cancel()
        self.process_finished_songs.cancel()
    
    @tasks.loop(minutes=1)
    async def check_inactivity(self):
        """Task to check for voice client inactivity."""
        await self.guild_music_state.check_inactivity()
    
    @check_inactivity.before_loop
    async def before_check_inactivity(self):
        await self.bot.wait_until_ready()
    
    async def join_voice_channel(self, ctx):
        """Join the user's voice channel."""
        if ctx.author.voice is None:
            await ctx.send("You need to be in a voice channel to use this command.")
            return False
        
        voice_channel = ctx.author.voice.channel
        
        if ctx.voice_client is None:
            voice_client = await voice_channel.connect()
            self.guild_music_state.voice_clients[ctx.guild.id] = voice_client
            return True
        elif ctx.voice_client.channel != voice_channel:
            await ctx.voice_client.move_to(voice_channel)
            return True
        
        return True
    
    async def play_next(self, ctx):
        """Play the next song in the queue."""
        # Verificar si el cliente de voz sigue conectado
        if not ctx.voice_client or not ctx.voice_client.is_connected():
            logger.info("Voice client disconnected, not playing next song")
            return
        
        # Verificar si ya está reproduciendo algo (evitar reproducción simultánea)
        if ctx.voice_client.is_playing():
            logger.info("Already playing something, not starting a new song")
            return
        
        queue = self.guild_music_state.get_queue(ctx.guild.id)
        queue.update_activity()
        
        # Guardar la canción actual para comparar después
        old_song = queue.current
        
        # La canción actual ya se reprodujo, así que obtenemos la siguiente
        song = queue.get_next()
        
        # Si no hay más canciones en la cola, desconectamos
        if not song:
            await ctx.send("Queue is empty. Stopping playback.")
            # Limpiar referencias antes de desconectar
            queue.current = None
            
            # Limpiar el canal de comando
            if ctx.guild.id in self.command_channels:
                del self.command_channels[ctx.guild.id]
            
            try:
                if ctx.voice_client and ctx.voice_client.is_connected():
                    await ctx.voice_client.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")
            return
        
        # Actualizar la canción actual a la nueva canción
        queue.current = song
        
        # Verificar nuevamente si el cliente de voz sigue conectado
        if not ctx.voice_client or not ctx.voice_client.is_connected():
            logger.info("Voice client disconnected before playing")
            return
        
        try:
            # Reproducir la canción actual
            if queue.current and queue.current.source:
                # Usar nuestro nuevo sistema de flags
                ctx.voice_client.play(
                    discord.PCMVolumeTransformer(queue.current.source, volume=queue.volume),
                    after=lambda _: self.bot.loop.call_soon_threadsafe(self.set_song_finished, ctx.guild.id)
                )
                
                # Solo enviar el embed si la canción cambió
                if old_song != queue.current:
                    embed = EmbedCreator.create_now_playing_embed(queue.current)
                    await ctx.send(embed=embed)
            else:
                logger.error("Error: Current song or source is None")
                await ctx.send("Error playing the current song. Skipping...")
        except Exception as e:
            logger.error(f"Error playing song: {e}")
    
    async def handle_song_complete(self, error, ctx):
        """Este método ya no se utiliza."""
        pass
    
    async def process_song(self, ctx, url, requester):
        """Process a song URL and add to queue."""
        queue = self.guild_music_state.get_queue(ctx.guild.id)
        queue.update_activity()
        
        async with ctx.typing():
            try:
                # Procesar la canción independientemente de si es una URL o una búsqueda
                sources = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True, volume=queue.volume)
                
                if not sources or len(sources) == 0:
                    return "Couldn't extract any audio from that URL or search term."
                
                # Process the song
                source_data = sources[0]
                song = Song(
                    source=source_data['source'],
                    title=source_data['data'].get('title', 'Unknown Title'),
                    duration=YTDLSource.parse_duration(source_data['data'].get('duration')),
                    url=source_data['data'].get('webpage_url', url),
                    thumbnail=source_data['data'].get('thumbnail'),
                    requester=requester
                )
                
                # Add to queue
                queue.add(song)
                
                # Start playing if not already playing
                if not ctx.voice_client.is_playing():
                    await self.play_next(ctx)
                    return None
                
                return f"Added **{song.title}** to the queue."
                    
            except Exception as e:
                logger.error(f"Error processing song: {e}")
                return f"An error occurred: {e}"
    
    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx, *, url):
        """Play a song from a YouTube URL."""
        # Verificar que es una URL válida
        if not url.startswith(('http://', 'https://')):
            await ctx.send("❌ Solo se aceptan URLs directas. Usa `fz!p https://www.youtube.com/watch?v=...`")
            return
        
        # Guardar el canal desde donde se ejecutó el comando
        self.command_channels[ctx.guild.id] = ctx.channel.id
        
        # Asegurarnos de que el bot está en un canal de voz
        if not await self.join_voice_channel(ctx):
            return
        
        # Procesar la canción
        result = await self.process_song(ctx, url, ctx.author)
        
        # Enviar confirmación si hay resultado
        if result:
            embed = EmbedCreator.create_basic_embed("✅ Añadido a la cola", result)
            await ctx.send(embed=embed)
    
    @commands.command(name="skip", aliases=["s"])
    async def skip(self, ctx):
        """Skip the current song."""
        # Actualizar el canal de comando
        self.command_channels[ctx.guild.id] = ctx.channel.id
        
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            await ctx.send("❌ No hay ninguna canción reproduciéndose actualmente.")
            return
        
        queue = self.guild_music_state.get_queue(ctx.guild.id)
        queue.update_activity()
        
        # Obtener el título de la canción antes de saltarla
        current_title = queue.current.title if queue.current else "Unknown"
        
        # Primero detener la reproducción actual
        ctx.voice_client.stop()
        
        # Eliminar código referente al modo loop
        # Ya no necesitamos esto:
        # old_loop_state = queue.loop
        # queue.loop = False
        # ...
        # queue.loop = old_loop_state
        
        # Enviar mensaje confirmando el salto
        await ctx.send(f"⏭️ **Saltada:** {current_title}")
    
    @commands.command(name="queue", aliases=["q", "qu"])
    async def queue_cmd(self, ctx, page: int = 1):
        """Display the current queue."""
        queue = self.guild_music_state.get_queue(ctx.guild.id)
        queue.update_activity()
        
        # Lista para mostrar la cola
        display_queue = []
        
        # Añadir canción actual si existe
        if queue.current:
            display_queue.append({"position": 0, "song": queue.current, "current": True})
        
        # Añadir canciones en cola
        for i, song in enumerate(queue.queue):
            display_queue.append({"position": i+1, "song": song, "current": False})
        
        if not display_queue:
            await ctx.send("La cola está vacía.")
            return
        
        # Ajustar número de página a índice base 0
        page_idx = max(0, page - 1)
        
        # Crear un embed elegante para mostrar la cola
        embed = discord.Embed(
            title="🎵 Cola de reproducción",
            color=0x9B59B6  # Color morado
        )
        
        # Determinar el número de canciones por página
        songs_per_page = 10
        pages = (len(display_queue) + songs_per_page - 1) // songs_per_page
        
        # Asegurarse de que la página solicitada existe
        if page_idx >= pages:
            page_idx = 0
        
        # Calcular las canciones para esta página
        start = page_idx * songs_per_page
        end = min(start + songs_per_page, len(display_queue))
        page_songs = display_queue[start:end]
        
        # Calcular la duración total de todas las canciones
        total_duration = "Unknown"
        
        # Añadir cada canción a la descripción
        description = ""
        for item in page_songs:
            song = item["song"]
            position = item["position"]
            if item["current"]:
                description += f"**🔊 Ahora:** {song.title} [{song.duration}] (pedida por {song.requester.display_name})\n\n"
            else:
                description += f"**{position}.** {song.title} [{song.duration}] (pedida por {song.requester.display_name})\n\n"
        
        embed.description = description
        
        # Añadir información de la página
        embed.set_footer(text=f"Página {page_idx+1} de {pages} | {len(display_queue)} canción(es) en total")
        
        await ctx.send(embed=embed)
    
    @commands.command(name="nowplaying", aliases=["np"])
    async def now_playing(self, ctx):
        """Display information about the currently playing song."""
        queue = self.guild_music_state.get_queue(ctx.guild.id)
        queue.update_activity()
        
        if not ctx.voice_client or not ctx.voice_client.is_playing() or not queue.current:
            await ctx.send("Nothing is playing right now.")
            return
        
        # Just use 0 for position since getting accurate position is difficult
        # without access to the internal player state
        position = 0
        
        embed = EmbedCreator.create_now_playing_embed(queue.current, position)
        await ctx.send(embed=embed)
    
    @commands.command(name="seek")
    async def seek(self, ctx, time_str: str):
        """Seek to a specific position in the song (format: MM:SS)."""
        # Método eliminado
    
    @commands.command(name="stop")
    async def stop(self, ctx):
        """Stop playback and clear the queue."""
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            await ctx.send("Nothing is playing right now.")
            return
        
        queue = self.guild_music_state.get_queue(ctx.guild.id)
        queue.update_activity()
        
        # Clear the queue and stop playing
        queue.clear()
        queue.current = None
        ctx.voice_client.stop()
        
        await ctx.send("⏹️ Playback stopped and queue cleared.")
    
    @commands.command(name="remove")
    async def remove(self, ctx, index: int):
        """Remove a specific song from the queue."""
        queue = self.guild_music_state.get_queue(ctx.guild.id)
        queue.update_activity()
        
        # Adjust index to 0-based
        idx = index - 1
        
        if idx < 0 or idx >= len(queue.queue):
            await ctx.send(f"Invalid index. Queue has {len(queue.queue)} songs.")
            return
        
        removed_song = queue.remove(idx)
        
        if removed_song:
            await ctx.send(f"🗑️ Removed **{removed_song.title}** from the queue.")
        else:
            await ctx.send("Failed to remove the song.")
    
    @commands.command(name="clear")
    async def clear(self, ctx):
        """Clear the entire queue."""
        queue = self.guild_music_state.get_queue(ctx.guild.id)
        queue.update_activity()
        
        queue.clear()
        await ctx.send("🧹 Queue cleared.")
    
    @commands.command(name="pause")
    async def pause(self, ctx):
        """Pause the current song."""
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            await ctx.send("Nothing is playing right now.")
            return
        
        queue = self.guild_music_state.get_queue(ctx.guild.id)
        queue.update_activity()
        
        ctx.voice_client.pause()
        await ctx.send("⏸️ Paused.")
    
    @commands.command(name="resume")
    async def resume(self, ctx):
        """Resume the paused song."""
        if not ctx.voice_client:
            await ctx.send("Not connected to a voice channel.")
            return
        
        queue = self.guild_music_state.get_queue(ctx.guild.id)
        queue.update_activity()
        
        if ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("▶️ Resumed.")
        else:
            await ctx.send("The music is not paused.")
    
    @commands.command(name="shuffle")
    async def shuffle(self, ctx):
        """Shuffle the queue."""
        # Método eliminado
    
    @commands.command(name="volume", aliases=["vol"])
    async def volume(self, ctx, volume: int):
        """Adjust the volume (1-100)."""
        if not ctx.voice_client:
            await ctx.send("Not connected to a voice channel.")
            return
        
        queue = self.guild_music_state.get_queue(ctx.guild.id)
        queue.update_activity()
        
        if not 0 <= volume <= 100:
            await ctx.send("Volume must be between 0 and 100.")
            return
        
        # Set volume for the queue (for future songs)
        queue.volume = volume / 100
        
        # Set volume for the current playback
        if ctx.voice_client.source:
            ctx.voice_client.source.volume = volume / 100
        
        await ctx.send(f"🔊 Volume set to {volume}%")
    
    @commands.command(name="dc", aliases=["disconnect"])
    async def disconnect(self, ctx):
        """Disconnect the bot from the voice channel."""
        if not ctx.voice_client:
            await ctx.send("Not connected to a voice channel.")
            return
        
        # Clear the queue for this guild
        if ctx.guild.id in self.guild_music_state.queues:
            del self.guild_music_state.queues[ctx.guild.id]
        
        # Disconnect
        await ctx.voice_client.disconnect()
        
        # Remove from voice clients dict
        if ctx.guild.id in self.guild_music_state.voice_clients:
            del self.guild_music_state.voice_clients[ctx.guild.id]
        
        await ctx.send("👋 Disconnected from voice channel.")
    
    @commands.command(name="help")
    async def help_command(self, ctx):
        """Show help for the music bot commands."""
        # Color morado (en hexadecimal)
        embed = discord.Embed(
            title="🎵 FzMusic - Comandos",
            description="Lista de comandos disponibles:",
            color=0x9B59B6  # Color morado
        )
        
        # Comandos básicos con sus aliases
        embed.add_field(
            name="Comandos básicos",
            value="`fz!play` o `fz!p` - Reproduce una canción desde YouTube (solo URLs directas)\n"
                  "`fz!skip` o `fz!s` - Salta la canción actual\n"
                  "`fz!queue` o `fz!q` o `fz!qu` - Muestra la cola de reproducción\n"
                  "`fz!pause` - Pausa la reproducción\n"
                  "`fz!resume` - Reanuda la reproducción",
            inline=False
        )
        
        # Comandos avanzados con sus aliases
        embed.add_field(
            name="Comandos avanzados",
            value="`fz!nowplaying` o `fz!np` - Muestra información sobre la canción actual\n"
                  "`fz!volume` o `fz!vol` - Ajusta el volumen (1-100)\n"
                  "`fz!clear` - Limpia la cola de reproducción\n"
                  "`fz!remove` - Elimina una canción específica de la cola por su número\n"
                  "`fz!dc` o `fz!disconnect` - Desconecta el bot del canal de voz",
            inline=False
        )
        
        embed.set_footer(text="FzMusic Bot")
        embed.timestamp = datetime.datetime.now()
        
        await ctx.send(embed=embed)
    
    @play.before_invoke
    async def ensure_voice(self, ctx):
        """Ensure the bot is in a voice channel before playing."""
        if not await self.join_voice_channel(ctx):
            raise commands.CommandError("Could not join voice channel.")

    def set_song_finished(self, guild_id):
        """Marca una canción como finalizada para su procesamiento posterior"""
        self.song_finished_flags[guild_id] = True

    @tasks.loop(seconds=0.5)
    async def process_finished_songs(self):
        """Procesa canciones que han finalizado de forma segura."""
        # Copiar el diccionario para evitar errores de modificación durante la iteración
        flags_to_process = self.song_finished_flags.copy()
        self.song_finished_flags.clear()
        
        for guild_id in flags_to_process:
            try:
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue
                
                # Usar el canal registrado si existe
                text_channel = None
                if guild_id in self.command_channels:
                    channel_id = self.command_channels[guild_id]
                    channel = guild.get_channel(channel_id)
                    if channel and channel.permissions_for(guild.me).send_messages:
                        text_channel = channel
                
                # Si no tenemos un canal registrado, buscar cualquiera como fallback
                if not text_channel:
                    for channel in guild.text_channels:
                        if channel.permissions_for(guild.me).send_messages:
                            text_channel = channel
                            break
                
                if not text_channel:
                    continue
                
                # Crear un contexto falso
                ctx = SimpleContext(self.bot, text_channel)
                
                # Obtener el cliente de voz
                voice_client = guild.voice_client
                if not voice_client:
                    continue
                
                # Solo reproducir la siguiente canción si no se está reproduciendo nada
                if not voice_client.is_playing():
                    # Verificar si hay una próxima canción antes de enviar el mensaje
                    queue = self.guild_music_state.get_queue(guild_id)
                    if queue and (queue.queue or queue.current):
                        await self.play_next(ctx)
                    # Si no hay una próxima canción, limpiamos
                    else:
                        # No hay más canciones, limpiamos las referencias
                        if guild_id in self.command_channels:
                            del self.command_channels[guild_id]
            except Exception as e:
                logger.error(f"Error processing finished song for guild {guild_id}: {e}")

    @process_finished_songs.before_loop
    async def before_process_finished_songs(self):
        await self.bot.wait_until_ready()

class SimpleContext:
    """Un contexto simple para usar cuando no tenemos un contexto de comando real."""
    def __init__(self, bot, channel):
        self.bot = bot
        self.channel = channel
        self.guild = channel.guild
        self.author = channel.guild.me
        self.voice_client = channel.guild.voice_client
    
    async def send(self, content=None, *, embed=None):
        try:
            return await self.channel.send(content=content, embed=embed)
        except Exception as e:
            logger.error(f"Error sending message in SimpleContext: {e}")
            return None

async def setup(bot):
    await bot.add_cog(Music(bot))