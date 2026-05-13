"""
Configuration Module
Centralized configuration management with environment variables and defaults.
"""

import os
from dataclasses import dataclass, field
from typing import Optional, List
from pathlib import Path


# Content limits
DEFAULT_REDDIT_UPVOTE_LIMIT = 10
DEFAULT_REDDIT_UPVOTE_DAYS = 14
DEFAULT_WORDPRESS_DAYS = 7
DEFAULT_WORDPRESS_POST_LIMIT = 10
DEFAULT_POSTS_PER_PLATFORM = 3
DEFAULT_TWITTER_TWEETS_DAYS = 7

# API settings
DEFAULT_OPENAI_MODEL = "gpt-4"
DEFAULT_OPENAI_API_BASE = "https://api.openai.com/v1"
DEFAULT_OPENAI_TEMPERATURE = 0.7
DEFAULT_OPENAI_MAX_TOKENS = 2000  # Increased for complex JSON responses

# Email settings
DEFAULT_SMTP_SERVER = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587

# Content settings
DEFAULT_LANGUAGE = "en"
CONTENT_PREVIEW_CHARS = 500
WORDPRESS_CONTENT_PREVIEW_CHARS = 1000
READING_SPEED_WPM = 200  # Words per minute for reading time calculation

# Performance settings
DEFAULT_MAX_CONCURRENT_REQUESTS = 5
DEFAULT_REQUEST_TIMEOUT = 60
DEFAULT_RETRY_MAX_ATTEMPTS = 3
DEFAULT_RETRY_INITIAL_DELAY = 1.0  # seconds
DEFAULT_RETRY_BACKOFF_FACTOR = 2.0

# Logging settings
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FILE = "social_content_bot.log"
DEFAULT_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_LOG_BACKUP_COUNT = 5


@dataclass
class RedditConfig:
    """Reddit API configuration."""
    client_id: str = ""
    client_secret: str = ""
    user_agent: str = "SocialContentBot/1.0"
    username: str = ""
    password: str = ""

    @property
    def is_configured(self) -> bool:
        # For upvoted posts access, need full authentication (client_id + username + password)
        return bool(self.client_id and self.username and self.password)


@dataclass
class WordPressConfig:
    """WordPress API configuration."""
    site_url: str = ""
    username: str = ""
    app_password: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.site_url)


@dataclass
class OpenAIConfig:
    """OpenAI API configuration."""
    api_key: str = ""
    api_base: str = DEFAULT_OPENAI_API_BASE
    model: str = DEFAULT_OPENAI_MODEL
    temperature: float = DEFAULT_OPENAI_TEMPERATURE
    max_tokens: int = DEFAULT_OPENAI_MAX_TOKENS

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


@dataclass
class EmailConfig:
    """Email/SMTP configuration."""
    smtp_server: str = DEFAULT_SMTP_SERVER
    smtp_port: int = DEFAULT_SMTP_PORT
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.smtp_username and self.smtp_password and self.email_to)


@dataclass
class TwitterConfig:
    """Twitter/X configuration using scweet for scraping.
    
    scweet uses browser cookies (auth_token) for authentication, NOT username/password.
    Username/password login is NOT supported and will trigger account locks.
    
    How to get your auth_token:
    1. Log in to x.com in Chrome/Firefox browser
    2. Open DevTools (F12) -> Application -> Cookies -> https://x.com
    3. Find and copy the 'auth_token' value
    4. Set TWITTER_AUTH_TOKEN environment variable
    
    Cookie format:
    - Single account: Set TWITTER_AUTH_TOKEN directly
    - Multiple accounts: Use cookies.json file with format:
      [
        {
          "username": "account_name",
          "cookies": {"auth_token": "...", "ct0": "..."}
        }
      ]
    
    Note: ct0 is optional - scweet auto-bootstraps it from auth_token
    """
    username: str = ""
    auth_token: str = ""           # Twitter auth_token from browser cookies (REQUIRED for single account)
    cookies_file: str = ""         # Path to cookies.json for multiple accounts (alternative to auth_token)
    proxy: str = ""                # Optional proxy for rate limiting avoidance

    @property
    def is_configured(self) -> bool:
        return bool(self.auth_token or self.cookies_file)


@dataclass
class BotConfig:
    # Content limits
    reddit_limit: int = DEFAULT_REDDIT_UPVOTE_LIMIT
    reddit_upvote_days: int = DEFAULT_REDDIT_UPVOTE_DAYS
    wordpress_days: int = DEFAULT_WORDPRESS_DAYS
    wordpress_limit: int = DEFAULT_WORDPRESS_POST_LIMIT
    posts_per_platform: int = DEFAULT_POSTS_PER_PLATFORM  # Legacy, kept for backward compatibility
    twitter_alternatives: int = DEFAULT_POSTS_PER_PLATFORM
    linkedin_alternatives: int = DEFAULT_POSTS_PER_PLATFORM
    language: str = DEFAULT_LANGUAGE

    # Execution options
    skip_reddit: bool = False
    skip_wordpress: bool = False
    dry_run: bool = False
    output_file: Optional[str] = None
    env_file: str = ".env"

    # Performance settings
    max_concurrent_requests: int = DEFAULT_MAX_CONCURRENT_REQUESTS
    request_timeout: int = DEFAULT_REQUEST_TIMEOUT
    retry_max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS
    retry_initial_delay: float = DEFAULT_RETRY_INITIAL_DELAY
    retry_backoff_factor: float = DEFAULT_RETRY_BACKOFF_FACTOR

    # Logging settings
    log_level: str = DEFAULT_LOG_LEVEL
    log_file: str = DEFAULT_LOG_FILE
    log_max_bytes: int = DEFAULT_LOG_MAX_BYTES
    log_backup_count: int = DEFAULT_LOG_BACKUP_COUNT
    twitter_prompt: str = ""
    linkedin_prompt: str = ""
    twitter_tweets_days: int = DEFAULT_TWITTER_TWEETS_DAYS


@dataclass
class Config:
    """Complete configuration container."""
    reddit: RedditConfig = field(default_factory=RedditConfig)
    wordpress: WordPressConfig = field(default_factory=WordPressConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    twitter: TwitterConfig = field(default_factory=TwitterConfig)
    bot: BotConfig = field(default_factory=BotConfig)

    @classmethod
    def from_env(cls, env_file: str = ".env") -> "Config":
        """
        Load configuration from environment variables.
        Supports loading from a specific .env file.
        """
        from dotenv import load_dotenv
        load_dotenv(env_file)

        config = cls()

        # Reddit configuration
        config.reddit.client_id = os.getenv("REDDIT_CLIENT_ID", "")
        config.reddit.client_secret = os.getenv("REDDIT_CLIENT_SECRET", "")
        config.reddit.user_agent = os.getenv("REDDIT_USER_AGENT", "SocialContentBot/1.0")
        config.reddit.username = os.getenv("REDDIT_USERNAME", "")
        config.reddit.password = os.getenv("REDDIT_PASSWORD", "")

        # WordPress configuration
        config.wordpress.site_url = os.getenv("WORDPRESS_SITE_URL", "")
        config.wordpress.username = os.getenv("WORDPRESS_USERNAME", "")
        config.wordpress.app_password = os.getenv("WORDPRESS_APP_PASSWORD", "")

        # OpenAI configuration
        config.openai.api_key = os.getenv("OPENAI_API_KEY", "")
        config.openai.api_base = os.getenv("OPENAI_API_BASE", DEFAULT_OPENAI_API_BASE)
        config.openai.model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)

        # Email configuration
        config.email.smtp_server = os.getenv("SMTP_SERVER", DEFAULT_SMTP_SERVER)
        config.email.smtp_port = int(os.getenv("SMTP_PORT", DEFAULT_SMTP_PORT))
        config.email.smtp_username = os.getenv("SMTP_USERNAME", "")
        config.email.smtp_password = os.getenv("SMTP_PASSWORD", "")
        config.email.email_from = os.getenv("EMAIL_FROM", "")
        config.email.email_to = os.getenv("EMAIL_TO", "")

        # Twitter configuration (scweet uses auth_token from browser cookies)
        config.twitter.username = os.getenv("TWITTER_USERNAME", "")
        config.twitter.auth_token = os.getenv("TWITTER_AUTH_TOKEN", "")
        config.twitter.cookies_file = os.getenv("TWITTER_COOKIES_FILE", "")
        config.twitter.proxy = os.getenv("TWITTER_PROXY", "")

        # Bot configuration from environment
        config.bot.reddit_limit = int(os.getenv("REDDIT_UPVOTE_LIMIT", DEFAULT_REDDIT_UPVOTE_LIMIT))
        config.bot.reddit_upvote_days = int(os.getenv("REDDIT_UPVOTE_DAYS", DEFAULT_REDDIT_UPVOTE_DAYS))
        config.bot.wordpress_limit = int(os.getenv("WORDPRESS_POST_LIMIT", DEFAULT_WORDPRESS_POST_LIMIT))
        config.bot.wordpress_days = int(os.getenv("WORDPRESS_DAYS", DEFAULT_WORDPRESS_DAYS))
        config.bot.twitter_tweets_days = int(os.getenv("TWITTER_TWEETS_DAYS", DEFAULT_TWITTER_TWEETS_DAYS))
        config.bot.posts_per_platform = int(os.getenv("POSTS_PER_PLATFORM", DEFAULT_POSTS_PER_PLATFORM))
        # Platform-specific alternatives (takes precedence over posts_per_platform if set)
        twitter_alt = os.getenv("TWITTER_ALTERNATIVES")
        linkedin_alt = os.getenv("LINKEDIN_ALTERNATIVES")
        if twitter_alt:
            config.bot.twitter_alternatives = int(twitter_alt)
        if linkedin_alt:
            config.bot.linkedin_alternatives = int(linkedin_alt)
        config.bot.language = os.getenv("CONTENT_LANGUAGE", DEFAULT_LANGUAGE)
        config.bot.log_level = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL)
        config.bot.log_file = os.getenv("LOG_FILE", DEFAULT_LOG_FILE)
        config.bot.twitter_prompt = os.getenv("TWITTER_SYSTEM_PROMPT", "")
        config.bot.linkedin_prompt = os.getenv("LINKEDIN_SYSTEM_PROMPT", "")
        
        # Performance settings from environment
        config.bot.max_concurrent_requests = int(os.getenv("MAX_CONCURRENT_REQUESTS", DEFAULT_MAX_CONCURRENT_REQUESTS))
        config.bot.request_timeout = int(os.getenv("REQUEST_TIMEOUT", DEFAULT_REQUEST_TIMEOUT))
        config.bot.retry_max_attempts = int(os.getenv("RETRY_MAX_ATTEMPTS", DEFAULT_RETRY_MAX_ATTEMPTS))

        return config

    @classmethod
    def validate(cls, config: "Config") -> List[str]:
        """
        Validate configuration and return list of issues.
        Returns empty list if configuration is valid.
        """
        issues = []

        # Check at least one source is configured
        if not config.reddit.is_configured and not config.wordpress.is_configured:
            issues.append("Either Reddit or WordPress must be configured")

        # Check OpenAI if content generation is needed
        if not config.openai.is_configured:
            issues.append("OpenAI API key not configured (OPENAI_API_KEY)")

        # Check email if not in dry-run mode
        if not config.bot.dry_run and not config.email.is_configured:
            issues.append("Email not configured (SMTP credentials and EMAIL_TO required)")

        return issues


# Global config instance
config: Optional[Config] = None


def get_config(env_file: str = ".env") -> Config:
    """Get or create the global configuration instance."""
    global config
    if config is None:
        config = Config.from_env(env_file)
    return config


def reset_config():
    """Reset the global configuration (useful for testing)."""
    global config
    config = None