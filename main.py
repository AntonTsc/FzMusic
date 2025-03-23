import discord
from discord.ext import commands
import os
import logging
import asyncio
from dotenv import load_dotenv
from keep_alive import keep_alive

# Add the project root to Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + '/..'))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# Load environment variables from .env file
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# Set up intents for the bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

# Initialize the bot with a command prefix and intents
bot = commands.Bot(command_prefix='fz!', intents=intents, help_command=None)

async def load_extensions():
    try:
        await bot.load_extension("src.cogs.music")
        print("Loaded music extension")
    except Exception as e:
        print(f"Failed to load extension: {e}")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print('------')

# Keep the bot running on Replit
keep_alive()

# Run the bot
async def main():
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())