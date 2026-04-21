import os
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime

import praw

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import get_config
from utils import get_logger, retry_with_backoff

console = Console()


@dataclass
class RedditUpvote:
    id: str
    title: str
    subreddit: str
    url: str
    permalink: str
    score: int
    num_comments: int
    author: str
    created_utc: datetime
    selftext: str
    link_flair_text: Optional[str]
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'title': self.title,
            'subreddit': self.subreddit,
            'url': self.url,
            'permalink': f"https://reddit.com{self.permalink}",
            'score': self.score,
            'num_comments': self.num_comments,
            'author': self.author,
            'created_utc': self.created_utc.isoformat(),
            'selftext': self.selftext[:500] if self.selftext else '',
            'link_flair_text': self.link_flair_text,
        }


class RedditClient:
    def __init__(self, client_id: str = None, client_secret: str = None, user_agent: str = None, username: str = None):
        cfg = get_config()
        self.client_id = client_id or cfg.reddit.client_id
        self.client_secret = client_secret or cfg.reddit.client_secret
        self.user_agent = user_agent or cfg.reddit.user_agent
        self.username = username or cfg.reddit.username
        self.logger = get_logger()
        
        if not all([self.client_id, self.client_secret, self.username]):
            raise ValueError(
                "Reddit credentials not configured. Set REDDIT_CLIENT_ID, "
                "REDDIT_CLIENT_SECRET, and REDDIT_USERNAME environment variables."
            )
        
        self.reddit = praw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            user_agent=self.user_agent,
            username=self.username,
            password=cfg.reddit.password,
        )
        
        console.print(f"[green]✓[/green] Reddit client initialized for user: {self.username}")

    @retry_with_backoff(exceptions=(Exception,))
    def get_upvoted_posts(self, limit: int = 10, max_age_days: int = 14) -> List[RedditUpvote]:
        upvotes = []
        skipped_old = 0
        
        console.print(f"\n[bold blue]Fetching {limit} upvoted posts from Reddit...[/bold blue]")
        
        try:
            redditor = self.reddit.redditor(self.username)
            
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
                task = progress.add_task("Downloading upvotes...", total=None)
                
                for i, submission in enumerate(redditor.upvoted(limit=limit * 3)):
                    if len(upvotes) >= limit:
                        break
                    
                    created_at = datetime.fromtimestamp(submission.created_utc)
                    age_days = (datetime.now() - created_at).days
                    
                    if age_days > max_age_days:
                        skipped_old += 1
                        continue
                    
                    upvote = RedditUpvote(
                        id=submission.id,
                        title=submission.title,
                        subreddit=str(submission.subreddit),
                        url=submission.url,
                        permalink=submission.permalink,
                        score=submission.score,
                        num_comments=submission.num_comments,
                        author=str(submission.author) if submission.author else '[deleted]',
                        created_utc=datetime.fromtimestamp(submission.created_utc),
                        selftext=submission.selftext,
                        link_flair_text=submission.link_flair_text,
                    )
                    upvotes.append(upvote)
                    progress.update(task, description=f"Fetched {i+1}/{limit} upvotes")
            
            self.logger.info(f"Successfully fetched {len(upvotes)} upvoted posts, skipped {skipped_old} older than {max_age_days} days")
            console.print(f"[green]✓[/green] Successfully fetched {len(upvotes)} upvoted posts")
            if skipped_old > 0:
                console.print(f"[dim]Skipped {skipped_old} posts older than {max_age_days} days[/dim]")
            
        except Exception as e:
            self.logger.error(f"Error fetching upvoted posts: {e}")
            console.print(f"[red]✗[/red] Error fetching upvoted posts: {e}")
            raise
        
        return upvotes

    def get_upvoted_posts_by_subreddit(self, limit: int = 10, subreddits: List[str] = None) -> Dict[str, List[RedditUpvote]]:
        all_upvotes = self.get_upvoted_posts(limit=limit)
        
        grouped = {}
        for upvote in all_upvotes:
            if subreddits and upvote.subreddit.lower() not in [s.lower() for s in subreddits]:
                continue
            
            if upvote.subreddit not in grouped:
                grouped[upvote.subreddit] = []
            grouped[upvote.subreddit].append(upvote)
        
        return grouped

    def format_upvote_for_content(self, upvote: RedditUpvote) -> str:
        content = f"""Title: {upvote.title}
Subreddit: r/{upvote.subreddit}
Author: u/{upvote.author}
Score: {upvote.score} upvotes
Comments: {upvote.num_comments}
URL: https://reddit.com{upvote.permalink}
"""
        
        if upvote.selftext:
            content += f"\nContent Preview:\n{upvote.selftext[:500]}...\n"
        
        return content