"""
Configuration module for the MCP Server (GIVEN - fully implemented)
Handles environment variables and application settings
"""

import os

# Server Configuration
PORT = int(os.getenv("PORT", "8080"))
HOST = os.getenv("HOST", "0.0.0.0")

# Database Configuration
DB_PATH = os.getenv("DB_PATH", "../database/support.db")

# Convert to absolute path if relative
if not os.path.isabs(DB_PATH):
    DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), DB_PATH))

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Validate configuration
if not (1 <= PORT <= 65535):
    raise ValueError(f"Invalid PORT: {PORT}. Must be between 1 and 65535")

if LOG_LEVEL not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
    raise ValueError(f"Invalid LOG_LEVEL: {LOG_LEVEL}")

# Ensure database directory exists
db_dir = os.path.dirname(DB_PATH)
if db_dir:
    os.makedirs(db_dir, exist_ok=True)


