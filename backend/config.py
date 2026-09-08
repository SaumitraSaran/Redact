"""
Configuration settings for RedactPro application.
"""

import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# Max upload size in megabytes (100MB default)
MAX_CONTENT_LENGTH = int(os.environ.get("UPLOAD_MAX_SIZE_MB", 100)) * 1024 * 1024

# Video limit in seconds
MAX_VIDEO_DURATION = float(os.environ.get("VIDEO_MAX_DURATION_SECONDS", 10.0))

# Server port and debug (default 5001 on macOS to avoid AirPlay conflict)
PORT = int(os.environ.get("FLASK_PORT", 5004))
DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1", "yes")

# Base temporary storage directory
TEMP_STORAGE_DIR = os.environ.get("REDACTPRO_TEMP_DIR", None)

# Allowed file extensions
ALLOWED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg",
    ".pdf",
    ".mp4", ".mov"
}
