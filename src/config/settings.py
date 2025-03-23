from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Configuration settings
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")  # Default to 'ffmpeg' if not set
PREFIX = "fz!"  # Command prefix for the bot

# Other settings can be added here as needed
