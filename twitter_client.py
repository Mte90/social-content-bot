from typing import Optional, List, Dict
from dataclasses import dataclass

from rich.console import Console

from config import get_config
from utils import get_logger

console = Console()


class TwitterClient:
    """Twitter client using scweet library for scraping data.
    
    Authentication: Uses browser cookies (auth_token), NOT username/password.
    Username/password login is NOT supported and will trigger account locks.
    """
    
    def __init__(
        self,
        auth_token: Optional[str] = None,
        cookies_file: Optional[str] = None,
        proxy: Optional[str] = None,
    ):
        cfg = get_config()
        self.auth_token = auth_token or cfg.twitter.auth_token
        self.cookies_file = cookies_file or cfg.twitter.cookies_file
        self.proxy = proxy or cfg.twitter.proxy
        self.logger = get_logger()

        if not self.auth_token and not self.cookies_file:
            raise ValueError(
                "Twitter auth_token not configured. Set TWITTER_AUTH_TOKEN environment variable "
                "or provide auth_token parameter. See config.py for instructions on getting auth_token from browser cookies."
            )

        self._scweet = None
        console.print(f"[green]✓[/green] Twitter client initialized")

    @property
    def scweet(self):
        if self._scweet is None:
            from Scweet.client import Scweet
            
            # Initialize with auth_token (preferred) or cookies_file
            kwargs = {
                "headless": True,
                "disable_images": True,
            }
            
            if self.proxy:
                kwargs["proxy"] = self.proxy
            
            if self.auth_token:
                kwargs["auth_token"] = self.auth_token
            elif self.cookies_file:
                kwargs["cookies_file"] = self.cookies_file
            
            self._scweet = Scweet(**kwargs)
        return self._scweet

    def post_tweet(self, text: str) -> bool:
        """
        Post a tweet to Twitter/X.
        
        Note: scweet is a scraping library and does not support posting tweets.
        This method is a placeholder for future implementation using Twitter API v2.
        
        To post tweets, you need to:
        1. Get Twitter API v2 credentials (Bearer Token, API Key, API Secret, Access Token)
        2. Use a library like tweepy or requests to post via Twitter API
        
        For now, this method logs the tweet content but does not actually post it.
        """
        try:
            self.logger.info(f"Tweet content prepared: {text[:50]}...")
            console.print(f"[cyan]Tweet prepared:[/cyan] {text[:50]}...")
            console.print(f"[yellow]⚠[/yellow] scweet does not support posting tweets. Use Twitter API v2 for posting.")
            console.print(f"[yellow]    Consider using 'tweepy' library with Twitter API credentials.[/yellow]")
            return False
        except Exception as e:
            self.logger.error(f"Error preparing tweet: {e}")
            console.print(f"[red]✗[/red] Error: {e}")
            return False

    def get_user_information(self, handle: str) -> Optional[Dict]:
        try:
            self.logger.info(f"Fetching user info for: {handle}")
            infos = self.scweet.get_user_information(
                handles=[handle],
                login=True,
            )
            return infos.get(handle) if infos else None
        except Exception as e:
            self.logger.error(f"Error fetching user information: {e}")
            console.print(f"[red]✗[/red] Error fetching user information: {e}")
            return None

    def get_followers(self, handle: str, limit: int = 100) -> List[str]:
        try:
            self.logger.info(f"Fetching followers for: {handle}")
            followers = self.scweet.get_followers(
                handle=handle,
                login=True,
                stay_logged_in=True,
                sleep=1,
            )
            return followers[:limit] if followers else []
        except Exception as e:
            self.logger.error(f"Error fetching followers: {e}")
            console.print(f"[red]✗[/red] Error fetching followers: {e}")
            return []

    def get_following(self, handle: str, limit: int = 100) -> List[str]:
        try:
            self.logger.info(f"Fetching following for: {handle}")
            following = self.scweet.get_following(
                handle=handle,
                login=True,
                stay_logged_in=True,
                sleep=1,
            )
            return following[:limit] if following else []
        except Exception as e:
            self.logger.error(f"Error fetching following: {e}")
            console.print(f"[red]✗[/red] Error fetching following: {e}")
            return []

    def get_profile_tweets(self, handle: str, limit: int = 50) -> List[Dict]:
        """Get tweets from a user's profile."""
        try:
            self.logger.info(f"Fetching tweets for: {handle}")
            tweets = self.scweet.get_profile_tweets(
                handle=handle,
                login=True,
                stay_logged_in=True,
                sleep=1,
            )
            return tweets[:limit] if tweets else []
        except Exception as e:
            self.logger.error(f"Error fetching tweets: {e}")
            console.print(f"[red]✗[/red] Error fetching tweets: {e}")
            return []