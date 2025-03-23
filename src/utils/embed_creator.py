import discord
import datetime
import math

class EmbedCreator:
    """Class to create consistent embeds for the music bot."""
    
    @staticmethod
    def create_basic_embed(title, description=None, color=0x3498db):
        """Create a basic embed with optional description."""
        embed = discord.Embed(
            title=title, 
            description=description, 
            color=color,
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text="FzMusic Bot")
        return embed
    
    @staticmethod
    def create_now_playing_embed(song, position=0):
        """Create an embed for the currently playing song."""
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"[{song.title}]({song.url})",
            color=0x1DB954  # Spotify green
        )
        
        # Add duration information if available
        if song.duration and song.duration != "Unknown duration":
            embed.add_field(name="Duration", value=f"`{song.duration}`", inline=True)
            
            # We could add a progress bar here, but we don't have accurate position tracking
            # For now, we'll just show the song duration
        
        embed.add_field(name="Requested by", value=song.requester.mention, inline=True)
        
        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)
            
        embed.set_footer(text="FzMusic Bot")
        embed.timestamp = datetime.datetime.now()
        
        return embed
    
    @staticmethod
    def create_queue_embed(queue, current_page=0, items_per_page=10):
        """Create an embed for displaying the queue."""
        queue_length = len(queue)
        pages = max(1, math.ceil(queue_length / items_per_page))
        current_page = min(current_page, pages - 1)
        
        start_idx = current_page * items_per_page
        end_idx = min(start_idx + items_per_page, queue_length)
        
        embed = discord.Embed(
            title="🎶 Music Queue",
            description=f"Showing page {current_page + 1}/{pages}" if pages > 1 else "Current queue",
            color=0xE74C3C
        )
        
        if queue_length == 0:
            embed.description = "The queue is empty. Add songs with `fz!play`!"
        else:
            queue_list = ""
            for i in range(start_idx, end_idx):
                song = queue[i]
                queue_list += f"**{i + 1}.** [{song.title}]({song.url}) | `{song.duration}` | Requested by: {song.requester.mention}\n"
            
            embed.description = f"**{queue_length} songs in queue | Page {current_page + 1}/{pages}**\n\n{queue_list}"
            
            # Add pagination info
            if pages > 1:
                embed.set_footer(text=f"Use 'fz!queue <page>' to view other pages | FzMusic Bot")
            else:
                embed.set_footer(text="FzMusic Bot")
        
        embed.timestamp = datetime.datetime.now()
        return embed
    
    @staticmethod
    def create_help_embed():
        """Create an embed for the help command."""
        embed = discord.Embed(
            title="FzMusic Bot Commands",
            description="Here are all available commands:",
            color=0x9B59B6
        )
        
        # Music commands
        embed.add_field(
            name="🎵 Music Commands",
            value=(
                "`fz!play <url>` - Play a song or add to queue (alias: `fz!p`)\n"
                "`fz!skip` - Skip to the next song (alias: `fz!s`)\n"
                "`fz!queue` - Show the current queue (alias: `fz!q`, `fz!qu`)\n"
                "`fz!np` - Show the currently playing song (alias: `fz!nowplaying`)\n"
                "`fz!pause` - Pause the current song\n"
                "`fz!resume` - Resume the paused song\n"
            ),
            inline=False
        )
        
        # Queue management
        embed.add_field(
            name="📋 Queue Management",
            value=(
                "`fz!remove <number>` - Remove a specific song from the queue\n"
                "`fz!clear` - Clear the entire queue\n"
            ),
            inline=False
        )
        
        # Playback control
        embed.add_field(
            name="🎚️ Playback Control",
            value=(
                "`fz!volume <1-100>` - Adjust the volume\n"
                "`fz!stop` - Stop playback and clear the queue\n"
                "`fz!dc` - Disconnect the bot from voice channel\n"
            ),
            inline=False
        )
        
        embed.set_footer(text="FzMusic Bot")
        embed.timestamp = datetime.datetime.now()
        
        return embed