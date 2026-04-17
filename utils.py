"""
Utility module with retry logic, logging, and rate limiting.
"""

import os
import sys
import time
import logging
import asyncio
import functools
from logging.handlers import RotatingFileHandler
from typing import Callable, TypeVar, Any, Optional, List
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import config, get_config, DEFAULT_LOG_LEVEL, DEFAULT_LOG_FILE, DEFAULT_LOG_MAX_BYTES, DEFAULT_LOG_BACKUP_COUNT

T = TypeVar('T')

logger: Optional[logging.Logger] = None


def setup_logging(log_level: str = None, log_file: str = None) -> logging.Logger:
    """Configure logging with rotation."""
    global logger
    
    if logger is not None:
        return logger
    
    cfg = get_config()
    level = log_level or cfg.bot.log_level or DEFAULT_LOG_LEVEL
    filename = log_file or cfg.bot.log_file or DEFAULT_LOG_FILE
    
    logger = logging.getLogger("social_content_bot")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    logger.handlers.clear()
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    try:
        file_handler = RotatingFileHandler(
            filename,
            maxBytes=cfg.bot.log_max_bytes or DEFAULT_LOG_MAX_BYTES,
            backupCount=cfg.bot.log_backup_count or DEFAULT_LOG_BACKUP_COUNT
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except (OSError, IOError) as e:
        logger.warning(f"Could not create log file {filename}: {e}")
    
    return logger


def get_logger() -> logging.Logger:
    """Get the configured logger."""
    global logger
    if logger is None:
        setup_logging()
    return logger


def retry_with_backoff(
    max_attempts: int = None,
    initial_delay: float = None,
    backoff_factor: float = None,
    exceptions: tuple = (Exception,)
) -> Callable:
    """Decorator for retrying functions with exponential backoff."""
    cfg = get_config()
    max_attempts = max_attempts or cfg.bot.retry_max_attempts
    initial_delay = initial_delay or cfg.bot.retry_initial_delay
    backoff_factor = backoff_factor or cfg.bot.retry_backoff_factor
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        get_logger().error(f"{func.__name__} failed after {max_attempts} attempts: {e}")
                        raise
                    get_logger().warning(
                        f"{func.__name__} attempt {attempt}/{max_attempts} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    delay *= backoff_factor
            
            raise last_exception
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts:
                        get_logger().error(f"{func.__name__} failed after {max_attempts} attempts: {e}")
                        raise
                    get_logger().warning(
                        f"{func.__name__} attempt {attempt}/{max_attempts} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                    delay *= backoff_factor
            
            raise last_exception
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper
    
    return decorator


def create_session_with_retries(
    max_retries: int = 3,
    backoff_factor: float = 0.5
) -> requests.Session:
    """Create a requests session with retry strategy."""
    session = requests.Session()
    
    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS", "TRACE"]
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session


class RateLimiter:
    """Rate limiter for API calls."""
    
    def __init__(self, calls_per_second: float = 1.0):
        self.calls_per_second = calls_per_second
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0.0
    
    async def acquire(self):
        """Acquire rate limit token (async)."""
        now = time.monotonic()
        elapsed = now - self.last_call
        
        if elapsed < self.min_interval:
            await asyncio.sleep(self.min_interval - elapsed)
        
        self.last_call = time.monotonic()
    
    def acquire_sync(self):
        """Acquire rate limit token (sync)."""
        now = time.monotonic()
        elapsed = now - self.last_call
        
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        
        self.last_call = time.monotonic()


async def gather_with_concurrency(n: int, *coros):
    """Run coroutines with limited concurrency."""
    semaphore = asyncio.Semaphore(n)
    
    async def sem_coro(coro):
        async with semaphore:
            return await coro
    
    return await asyncio.gather(*(sem_coro(c) for c in coros))


def ensure_dir(path: str) -> Path:
    """Ensure directory exists."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p