import asyncio
import random
from async_timeout import timeout
from discord.ext import commands

class Song:
    """Class representing a song."""
    def __init__(self, source, title, duration, url, thumbnail, requester):
        self.source = source
        self.title = title
        self.duration = duration
        self.url = url
        self.thumbnail = thumbnail
        self.requester = requester
        
    def __str__(self):
        return f"{self.title} ({self.duration})"

class MusicQueue:
    """Class to manage the music queue for a server."""
    def __init__(self, bot):
        self.bot = bot
        self.queue = []
        self.current = None
        self.loop = False
        self.volume = 0.5  # Default volume (0.5 = 50%)
        self.last_activity = None
        self._cog = None
    
    def __len__(self):
        return len(self.queue)
    
    @property
    def is_empty(self):
        """Return True if queue is empty."""
        return len(self.queue) == 0
    
    def clear(self):
        """Clear the queue."""
        self.queue.clear()
    
    def shuffle(self):
        """Shuffle the queue."""
        random.shuffle(self.queue)
    
    def add(self, song):
        """Add a song to the queue."""
        self.queue.append(song)
    
    def remove(self, index):
        """Remove a song at a specific index."""
        if 0 <= index < len(self.queue):
            return self.queue.pop(index)
        return None
    
    def get_next(self):
        """Get the next song in the queue."""
        if not self.queue:
            return None
        # Retorna y elimina la primera canción de la cola
        return self.queue.pop(0)
    
    def update_activity(self):
        """Update the last activity timestamp."""
        self.last_activity = asyncio.get_event_loop().time()

class GuildMusicState:
    """Class to manage music state across multiple guilds."""
    def __init__(self, bot):
        self.bot = bot
        self.voice_clients = {}
        self.queues = {}
        self.inactivity_timeout = 300  # 5 minutes in seconds
        
    def get_queue(self, guild_id):
        """Get or create a queue for a guild."""
        if guild_id not in self.queues:
            self.queues[guild_id] = MusicQueue(self.bot)
        return self.queues[guild_id]
    
    async def check_inactivity(self):
        """Check for voice client inactivity and disconnect if necessary."""
        while True:
            await asyncio.sleep(60)  # Check every minute
            current_time = asyncio.get_event_loop().time()
            
            for guild_id, queue in list(self.queues.items()):
                if guild_id in self.voice_clients and queue.last_activity:
                    if current_time - queue.last_activity > self.inactivity_timeout:
                        voice_client = self.voice_clients[guild_id]
                        if voice_client.is_connected():
                            await voice_client.disconnect()
                            if guild_id in self.queues:
                                del self.queues[guild_id]
                            if guild_id in self.voice_clients:
                                del self.voice_clients[guild_id]