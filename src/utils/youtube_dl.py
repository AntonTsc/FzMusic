import asyncio
import re
import yt_dlp
import discord
import logging

logger = logging.getLogger('youtube_dl')

# Custom YoutubeDL options
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',  # IPv4 address for connection
    'extract_flat': 'in_playlist',
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('webpage_url')
        self.duration = self.parse_duration(data.get('duration'))
        self.thumbnail = data.get('thumbnail')
    
    @staticmethod
    def parse_duration(duration):
        if not duration:
            return "Unknown duration"
        
        minutes, seconds = divmod(int(duration), 60)
        hours, minutes = divmod(minutes, 60)
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
    
    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False, volume=0.5, playlist_items=None):
        """Extract info and create a source for a YouTube URL or search term."""
        loop = loop or asyncio.get_event_loop()
        
        # Create a copy of ytdl_format_options to modify
        format_options = ytdl_format_options.copy()
        
        # If playlist_items is specified, add it to the options (we'll keep this for potential future use)
        if playlist_items:
            format_options['playlist_items'] = playlist_items
        
        # For search terms, force selecting only the first result
        if url.startswith('ytsearch:'):
            format_options['default_search'] = 'ytsearch1'
        
        # Create a new YoutubeDL instance with the modified options
        ytdl_instance = yt_dlp.YoutubeDL(format_options)
        
        try:
            # Run the extraction in a separate thread to avoid blocking
            data = await loop.run_in_executor(None, lambda: ytdl_instance.extract_info(url, download=not stream))
            
            if data is None:
                logger.error(f"Failed to extract info from {url}")
                return []
            
            if 'entries' in data:
                # Take only the first entry from playlist/search results
                entries = [entry for entry in data['entries'] if entry is not None]
                if not entries:
                    return []
                # Just take the first result for search queries
                data = entries[0]
            
            # Create the audio source
            source = cls.process_entry(data, stream, volume)
            return [source] if source else []
        except Exception as e:
            logger.error(f"Error in YTDLSource.from_url: {e}")
            return []
        
    @staticmethod
    def process_entry(entry, stream=False, volume=0.5):
        """Process a single entry from ytdl extraction."""
        try:
            # For streamed sources, we need to get the direct URL
            if stream:
                url = entry['url']
                ffmpeg_options = {
                    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                    'options': '-vn'
                }
                source = discord.FFmpegPCMAudio(url, **ffmpeg_options)
                
                # Apply volume transformation
                transformed_source = discord.PCMVolumeTransformer(source, volume=volume)
                
                return {
                    'source': transformed_source,
                    'data': entry
                }
            else:
                # For downloaded sources (not used in this bot)
                return None
        except Exception as e:
            logger.error(f"Error processing entry: {e}")
            return None
    
    @staticmethod
    def is_playlist(url):
        """Check if the URL is a playlist."""
        # Patrones comunes para playlists de YouTube
        playlist_patterns = [
            r'(https?://)?(www\.)?(youtube\.com|youtu\.?be).*[&?]list=',
            r'(https?://)?(www\.)?youtube\.com/playlist\?'
        ]
        
        for pattern in playlist_patterns:
            if re.search(pattern, url):
                return True
        return False

    @staticmethod
    async def extract_playlist_urls(url, *, loop=None):
        """Extract individual video URLs from a playlist."""
        loop = loop or asyncio.get_event_loop()
        
        # Use a simpler format to just get video URLs and not actual audio
        format_options = {
            'extract_flat': True,
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
        }
        
        ytdl_instance = yt_dlp.YoutubeDL(format_options)
        
        try:
            # Este es el método correcto para ejecutar código bloqueante en un loop
            data = await loop.run_in_executor(None, lambda: ytdl_instance.extract_info(url, download=False))
            
            # Extract individual video URLs from the playlist
            if 'entries' in data:
                # Return list of video URLs - usamos los URLs directos si están disponibles, o creamos URLs desde los IDs
                return [entry.get('url', f"https://www.youtube.com/watch?v={entry['id']}") 
                        for entry in data['entries'] if entry.get('url') or entry.get('id')]
            return []
        except Exception as e:
            logger.error(f"Error extracting playlist URLs: {e}")
            return []