"""Application configuration and constants."""

import logging
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BACKEND_ROOT = PROJECT_ROOT / "backend"
LOG_DIR = PROJECT_ROOT / "logs"

# Server configuration
API_HOST = "127.0.0.1"
API_PORT = 8456
WEBSOCKET_PORT = 8457

# Device connection
DEVICE_POLL_INTERVAL_SECONDS = 2.0
DEVICE_CONNECTION_TIMEOUT_SECONDS = 10.0

# iOS version thresholds
IOS_17_VERSION = "17.0"

# Simulation defaults
DEFAULT_WALKING_SPEED_KMH = 5.0
DEFAULT_CYCLING_SPEED_KMH = 15.0
DEFAULT_DRIVING_SPEED_KMH = 60.0
SIMULATION_UPDATE_INTERVAL_SECONDS = 1.0
GPS_DRIFT_SIGMA_METERS = 2.0

# Logging configuration
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_LEVEL = logging.DEBUG


def setup_logging(level: int = LOG_LEVEL) -> None:
    """Configure application-wide logging.

    Args:
        level: The logging level to use. Defaults to LOG_LEVEL from config.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger("ios_gps_spoofer")
    root_logger.setLevel(level)

    # Avoid adding duplicate handlers
    if root_logger.handlers:
        return

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root_logger.addHandler(console_handler)

    # File handler
    file_handler = logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root_logger.addHandler(file_handler)
