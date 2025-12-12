import sys
from loguru import logger
from src.config import Config

def setup_logger():
    """
    Configures the Loguru logger.
    """
    logger.remove() # Remove default handler
    
    # Add console handler with color
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=Config.LOG_LEVEL,
        colorize=True
    )
    
    # Add file handler for structured logging (JSON or regular text)
    logger.add(
        "logs/app.log",
        rotation="1 day",
        retention="7 days",
        level=Config.LOG_LEVEL,
        compression="zip"
    )

# Initialize logger on module import
setup_logger()
