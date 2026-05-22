#!/usr/bin/env python3

import os
import sys
import argparse
import json
import asyncio
from datetime import datetime
from typing import List, Dict, Optional

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from config import Config, get_config, reset_config
from utils import setup_logging, get_logger

from reddit_client import RedditClient, RedditUpvote
from wordpress_client import WordPressClient, WordPressPost
from twitter_client import TwitterClient
from content_generator import ContentGenerator, SocialPostSuggestion, SocialPlatform
from email_sender import EmailSender

console = Console()


class SocialContentBot:
    def __init__(self, config: Config):
        self.config = config
        self.logger = get_logger()
        
        self._reddit_client: Optional[RedditClient] = None
        self._wordpress_client: Optional[WordPressClient] = None
        self._twitter_client: Optional[TwitterClient] = None
        self._content_generator: Optional[ContentGenerator] = None
        self._email_sender: Optional[EmailSender] = None
        
        self.reddit_upvotes: List[RedditUpvote] = []
        self.wordpress_posts: List[WordPressPost] = []
        self.twitter_tweets: List[Dict] = []
        self.suggestions: Dict[str, List[SocialPostSuggestion]] = {
            'reddit': [],
            'wordpress': [],
            'twitter': [],
        }
        self.repost_suggestions: Dict = {}
    
    @property
    def reddit_client(self) -> RedditClient:
        if self._reddit_client is None:
            self._reddit_client = RedditClient()
        return self._reddit_client
    
    @property
    def wordpress_client(self) -> WordPressClient:
        if self._wordpress_client is None:
            self._wordpress_client = WordPressClient()
        return self._wordpress_client

    @property
    def twitter_client(self) -> TwitterClient:
        if self._twitter_client is None and self.config.twitter.is_configured:
            self._twitter_client = TwitterClient()
        return self._twitter_client

    @property
    def content_generator(self) -> ContentGenerator:
        if self._content_generator is None:
            self._content_generator = ContentGenerator()
        return self._content_generator
    
    @property
    def email_sender(self) -> EmailSender:
        if self._email_sender is None:
            self._email_sender = EmailSender()
        return self._email_sender

    def fetch_reddit_upvotes(self) -> List[RedditUpvote]:
        console.print("\n[bold blue]━━━ Fetching Reddit Upvotes ━━━[/bold blue]")
        
        try:
            self.reddit_upvotes = self.reddit_client.get_upvoted_posts(
                limit=self.config.bot.reddit_limit,
                max_age_days=self.config.bot.reddit_upvote_days
            )
            return self.reddit_upvotes
        except Exception as e:
            self.logger.error(f"Error fetching Reddit upvotes: {e}")
            console.print(f"[red]Error fetching Reddit upvotes: {e}[/red]")
            return []

    def fetch_wordpress_posts(self) -> List[WordPressPost]:
        console.print("\n[bold blue]━━━ Fetching WordPress Posts ━━━[/bold blue]")
        
        try:
            self.wordpress_posts = self.wordpress_client.get_posts(
                days=self.config.bot.wordpress_days
            )
            return self.wordpress_posts
        except Exception as e:
            self.logger.error(f"Error fetching WordPress posts: {e}")
            console.print(f"[red]Error fetching WordPress posts: {e}[/red]")
            return []

    def fetch_twitter_tweets(self) -> List[Dict]:
        console.print("\n[bold blue]━━━ Fetching My Recent Tweets ━━━[/bold blue]")
        
        if not self.twitter_client:
            console.print("[yellow]Twitter not configured, skipping[/yellow]")
            return []
        
        try:
            tweets = self.twitter_client.get_profile_tweets(
                handle=self.config.twitter.username,
                limit=self.config.bot.twitter_alternatives * 3,
                max_age_days=self.config.bot.twitter_tweets_days,
            )
            self.twitter_tweets = tweets
            console.print(f"[green]✓[/green] Fetched {len(tweets)} recent tweets (max {self.config.bot.twitter_tweets_days} days old)")
            return tweets
        except Exception as e:
            self.logger.error(f"Error fetching tweets: {e}")
            console.print(f"[red]Error fetching tweets: {e}[/red]")
            return []

    async def generate_suggestions_async(self) -> Dict[str, List[SocialPostSuggestion]]:
        console.print("\n[bold blue]━━━ Generating Content Suggestions ━━━[/bold blue]")
        
        # Build platform-specific counts dict from config
        platform_counts = {
            SocialPlatform.TWITTER: self.config.bot.twitter_alternatives,
            SocialPlatform.LINKEDIN: self.config.bot.linkedin_alternatives,
        }
        
        if self.reddit_upvotes:
            console.print(f"\n[cyan]Generating suggestions for {len(self.reddit_upvotes)} Reddit upvotes...[/cyan]")
            
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), console=console) as progress:
                task = progress.add_task("Processing Reddit...", total=len(self.reddit_upvotes))
                
                tasks = []
                for upvote in self.reddit_upvotes:
                    tasks.append(
                        self.content_generator.generate_from_reddit_upvote_async(
                            upvote.to_dict(),
                            posts_per_platform=self.config.bot.twitter_alternatives,  # Reddit only generates Twitter posts
                        )
                    )                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for i, result in enumerate(results):
                    upvote = self.reddit_upvotes[i]
                    if isinstance(result, Exception):
                        self.logger.warning(f"Could not generate suggestions for '{upvote.title[:30]}...': {result}")
                        console.print(f"[yellow]Warning: Could not generate suggestions for '{upvote.title[:30]}...': {result}[/yellow]")
                    else:
                        self.suggestions['reddit'].extend(result)
                    
                    progress.advance(task)
        
        if self.wordpress_posts:
            console.print(f"\n[cyan]Generating suggestions for {len(self.wordpress_posts)} WordPress posts...[/cyan]")
            
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), console=console) as progress:
                task = progress.add_task("Processing WordPress...", total=len(self.wordpress_posts))
                
                tasks = []
                for post in self.wordpress_posts:
                    tasks.append(
                        self.content_generator.generate_from_wordpress_post_async(
                            post.to_dict(),
                            posts_per_platform=self.config.bot.linkedin_alternatives,  # WordPress only generates LinkedIn posts
                        )
                    )                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for i, result in enumerate(results):
                    post = self.wordpress_posts[i]
                    if isinstance(result, Exception):
                        self.logger.warning(f"Could not generate suggestions for '{post.title[:30]}...': {result}")
                        console.print(f"[yellow]Warning: Could not generate suggestions for '{post.title[:30]}...': {result}[/yellow]")
                    else:
                        self.suggestions['wordpress'].extend(result)
                    
                    progress.advance(task)
        
        if self.twitter_tweets:
            console.print(f"\n[cyan]Generating suggestions for {len(self.twitter_tweets)} tweets...[/cyan]")
            
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), console=console) as progress:
                task = progress.add_task("Processing Tweets...", total=len(self.twitter_tweets))
                
                tasks = []
                for tweet in self.twitter_tweets:
                    tasks.append(
                        self.content_generator.generate_from_tweet_async(
                            tweet,
                            posts_per_platform=self.config.bot.linkedin_alternatives,
                        )
                    )
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for i, result in enumerate(results):
                    tweet = self.twitter_tweets[i]
                    if isinstance(result, Exception):
                        self.logger.warning(f"Could not generate suggestions for tweet: {result}")
                        console.print(f"[yellow]Warning: Could not generate suggestions for tweet: {result}[/yellow]")
                    else:
                        self.suggestions['twitter'].extend(result)
                    
                    progress.advance(task)
            
            console.print(f"\n[cyan]Analyzing tweets for repost suggestions...[/cyan]")
            self.repost_suggestions = await self.content_generator.suggest_reposts_async(self.twitter_tweets)
        
        total_suggestions = len(self.suggestions['reddit']) + len(self.suggestions['wordpress']) + len(self.suggestions['twitter'])
        self.logger.info(f"Generated {total_suggestions} total suggestions")
        console.print(f"\n[green]✓ Generated {total_suggestions} total suggestions[/green]")
        console.print(f"   - From Reddit: {len(self.suggestions['reddit'])}")
        console.print(f"   - From WordPress: {len(self.suggestions['wordpress'])}")
        console.print(f"   - From My Tweets: {len(self.suggestions['twitter'])}")
        
        return self.suggestions

    def generate_suggestions(self) -> Dict[str, List[SocialPostSuggestion]]:
        console.print("\n[bold blue]━━━ Generating Content Suggestions ━━━[/bold blue]")
        
        if self.reddit_upvotes:
            console.print(f"\n[cyan]Generating suggestions for {len(self.reddit_upvotes)} Reddit upvotes...[/cyan]")
            
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), console=console) as progress:
                task = progress.add_task("Processing Reddit...", total=len(self.reddit_upvotes))
                
                for upvote in self.reddit_upvotes:
                    try:
                        suggestions = self.content_generator.generate_from_reddit_upvote(
                            upvote.to_dict(),
                            posts_per_platform=self.config.bot.twitter_alternatives,
                        )
                        self.suggestions['reddit'].extend(suggestions)
                    except Exception as e:
                        self.logger.warning(f"Could not generate suggestions for '{upvote.title[:30]}...': {e}")
                        console.print(f"[yellow]Warning: Could not generate suggestions for '{upvote.title[:30]}...': {e}[/yellow]")
                    
                    progress.advance(task)
        
        if self.wordpress_posts:
            console.print(f"\n[cyan]Generating suggestions for {len(self.wordpress_posts)} WordPress posts...[/cyan]")
            
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), console=console) as progress:
                task = progress.add_task("Processing WordPress...", total=len(self.wordpress_posts))
                
                for post in self.wordpress_posts:
                    try:
                        suggestions = self.content_generator.generate_from_wordpress_post(
                            post.to_dict(),
                            posts_per_platform=self.config.bot.linkedin_alternatives,
                        )
                        self.suggestions['wordpress'].extend(suggestions)
                    except Exception as e:
                        self.logger.warning(f"Could not generate suggestions for '{post.title[:30]}...': {e}")
                        console.print(f"[yellow]Warning: Could not generate suggestions for '{post.title[:30]}...': {e}[/yellow]")
                    
                    progress.advance(task)
        
        if self.twitter_tweets:
            console.print(f"\n[cyan]Generating suggestions for {len(self.twitter_tweets)} tweets...[/cyan]")
            
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), console=console) as progress:
                task = progress.add_task("Processing Tweets...", total=len(self.twitter_tweets))
                
                for tweet in self.twitter_tweets:
                    try:
                        suggestions = self.content_generator.generate_from_tweet(
                            tweet,
                            posts_per_platform=self.config.bot.linkedin_alternatives,
                        )
                        self.suggestions['twitter'].extend(suggestions)
                    except Exception as e:
                        self.logger.warning(f"Could not generate suggestions for tweet: {e}")
                        console.print(f"[yellow]Warning: Could not generate suggestions for tweet: {e}[/yellow]")
                    
                    progress.advance(task)
            
            console.print(f"\n[cyan]Analyzing tweets for repost suggestions...[/cyan]")
            self.repost_suggestions = self.content_generator.suggest_reposts(self.twitter_tweets)
        
        total_suggestions = len(self.suggestions['reddit']) + len(self.suggestions['wordpress']) + len(self.suggestions['twitter'])
        self.logger.info(f"Generated {total_suggestions} total suggestions")
        console.print(f"\n[green]✓ Generated {total_suggestions} total suggestions[/green]")
        console.print(f"   - From Reddit: {len(self.suggestions['reddit'])}")
        console.print(f"   - From WordPress: {len(self.suggestions['wordpress'])}")
        console.print(f"   - From My Tweets: {len(self.suggestions['twitter'])}")
        
        return self.suggestions

    def send_email(self, to_email: str = None) -> bool:
        if self.config.bot.dry_run:
            console.print("\n[yellow]Dry run mode - skipping email send[/yellow]")
            return True
        
        console.print("\n[bold blue]━━━ Sending Email ━━━[/bold blue]")
        
        reddit_suggestions = [s.to_dict() for s in self.suggestions['reddit']]
        wordpress_suggestions = [s.to_dict() for s in self.suggestions['wordpress']]
        twitter_suggestions = [s.to_dict() for s in self.suggestions['twitter']]
        reddit_items = [u.to_dict() for u in self.reddit_upvotes]
        wordpress_items = [p.to_dict() for p in self.wordpress_posts]
        twitter_items = [t for t in self.twitter_tweets]
        
        try:
            return self.email_sender.send_digest(
                to_email=to_email,
                reddit_suggestions=reddit_suggestions,
                wordpress_suggestions=wordpress_suggestions,
                twitter_suggestions=twitter_suggestions,
                reddit_items=reddit_items,
                wordpress_items=wordpress_items,
                twitter_items=twitter_items,
                repost_suggestions=self.repost_suggestions,
            )
        except Exception as e:
            self.logger.error(f"Error sending email: {e}")
            console.print(f"[red]Error sending email: {e}[/red]")
            return False

    def display_suggestions(self):
        console.print("\n[bold blue]━━━ Generated Suggestions ━━━[/bold blue]")
        
        if self.suggestions['reddit']:
            console.print("\n[bold cyan]From Reddit Upvotes:[/bold cyan]")
            for suggestion in self.suggestions['reddit']:
                console.print(suggestion.format_for_display())
        
        if self.suggestions['wordpress']:
            console.print("\n[bold cyan]From WordPress Posts:[/bold cyan]")
            for suggestion in self.suggestions['wordpress']:
                console.print(suggestion.format_for_display())
        
        if self.suggestions['twitter']:
            console.print("\n[bold cyan]From My Tweets:[/bold cyan]")
            for suggestion in self.suggestions['twitter']:
                console.print(suggestion.format_for_display())

    def test_connections(self):
        """Test service connections and display status."""
        console.print(Panel.fit(
            "[bold blue]🔍 Testing Service Connections[/bold blue]",
            border_style="blue",
        ))
        
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Service", style="white")
        table.add_column("Configured", style="white")
        table.add_column("Status", style="white")
        table.add_column("Details", style="dim")
        
        # Reddit - actual login test
        reddit_configured = self.config.reddit.is_configured
        reddit_status = "[red]✗[/red]"
        reddit_details = "Missing credentials"
        
        if reddit_configured:
            try:
                # Initialize Reddit client which will authenticate
                reddit_client = self.reddit_client
                # Try to fetch a single upvoted post to verify login works
                redditor = reddit_client.reddit.redditor(reddit_client.username)
                list(redditor.upvoted(limit=1))
                reddit_status = "[green]✓[/green]"
                reddit_details = f"Logged in as u/{reddit_client.username}"
            except Exception as e:
                reddit_status = "[red]✗[/red]"
                reddit_details = f"Login failed: {str(e)}"
        
        table.add_row("Reddit", "Yes" if reddit_configured else "No", reddit_status, reddit_details)
        
        # WordPress - actual API connection test
        wp_configured = self.config.wordpress.is_configured
        wp_status = "[red]✗[/red]"
        wp_details = "Missing credentials"
        
        if wp_configured:
            try:
                wp_client = self.wordpress_client
                # Verify API access with a test request (5 second timeout)
                response = wp_client.session.get(
                    f"{wp_client.api_url}/posts",
                    params={'per_page': 1},
                    auth=wp_client.auth,
                    timeout=5
                )
                response.raise_for_status()
                wp_status = "[green]✓[/green]"
                auth_info = "Authenticated" if wp_client.auth else "Public access only"
                wp_details = f"{auth_info} - {wp_client.site_url}"
            except Exception as e:
                wp_status = "[red]✗[/red]"
                wp_details = f"Connection failed: {str(e)}"
        
        table.add_row("WordPress", "Yes" if wp_configured else "No", wp_status, wp_details)
        
        # Twitter - actual auth token test using get_user_information
        twitter_configured = self.config.twitter.is_configured
        twitter_status = "[red]✗[/red]"
        twitter_details = "Missing credentials"
        
        if twitter_configured:
            try:
                twitter_client = self.twitter_client
                # Try to get info for the configured username (or a known test user)
                # We use 'twitter' as a test handle since the client was initialized with auth_token
                twitter_client.scweet  # Trigger lazy initialization
                # Test with a known account - using 'twitter' as it's always available
                user_info = twitter_client.get_user_information('twitter')
                if user_info:
                    twitter_status = "[green]✓[/green]"
                    twitter_details = f"Authenticated - {user_info.get('username', 'user')}"
                else:
                    twitter_status = "[yellow]⚠[/yellow]"
                    twitter_details = "Auth token set but verification failed"
            except Exception as e:
                twitter_status = "[red]✗[/red]"
                twitter_details = f"Authentication failed: {str(e)}"
        
        table.add_row("Twitter (scweet)", "Yes" if twitter_configured else "No", twitter_status, twitter_details)
        
        # Email - actual SMTP connection test
        email_configured = self.config.email.is_configured
        email_status = "[red]✗[/red]"
        email_details = "Missing credentials"
        
        if email_configured:
            try:
                email_sender = self.email_sender
                # Test SMTP connection with actual login
                import smtplib
                with smtplib.SMTP(email_sender.smtp_server, email_sender.smtp_port) as server:
                    server.starttls()
                    server.login(email_sender.smtp_username, email_sender.smtp_password)
                    # Test send a minimal email
                    from email.mime.text import MIMEText
                    msg = MIMEText("Test connection from Social Content Bot")
                    msg['Subject'] = "Test Connection"
                    msg['From'] = email_sender.email_from
                    msg['To'] = email_sender.email_from  # Send to self
                    server.send_message(msg)
                
                email_status = "[green]✓[/green]"
                email_details = f"Connected to {email_sender.smtp_server}:{email_sender.smtp_port}"
            except Exception as e:
                email_status = "[red]✗[/red]"
                email_details = f"SMTP connection failed: {str(e)}"
        
        table.add_row("Email", "Yes" if email_configured else "No", email_status, email_details)
        
        console.print(table)
        
        # Summary
        total = 4
        # Count services that passed the connection test (status is green)
        configured = sum([
            1 if reddit_status == "[green]✓[/green]" else 0,
            1 if wp_status == "[green]✓[/green]" else 0,
            1 if twitter_status == "[green]✓[/green]" else 0,
            1 if email_status == "[green]✓[/green]" else 0,
        ])
        console.print(f"\n[bold]Summary:[/bold] {configured}/{total} services working")
        
        if configured == 0:
            console.print("\n[yellow]⚠️  No services configured. Check your .env file.[/yellow]")

    def save_to_json(self, filepath: str):
        data = {
            'timestamp': datetime.now().isoformat(),
            'reddit_upvotes': [u.to_dict() for u in self.reddit_upvotes],
            'wordpress_posts': [p.to_dict() for p in self.wordpress_posts],
            'twitter_tweets': self.twitter_tweets,
            'suggestions': {
                'reddit': [s.to_dict() for s in self.suggestions['reddit']],
                'wordpress': [s.to_dict() for s in self.suggestions['wordpress']],
                'twitter': [s.to_dict() for s in self.suggestions['twitter']],
            },
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Data saved to {filepath}")
        console.print(f"[green]✓[/green] Data saved to {filepath}")

    def run(self, skip_reddit: bool = False, skip_wordpress: bool = False, use_async: bool = True) -> bool:
        console.print(Panel.fit(
            "[bold blue]🤖 Social Content Bot[/bold blue]\n"
            "Generating social media suggestions from your content",
            border_style="blue",
        ))
        
        self.logger.info("Starting Social Content Bot workflow")
        
        if not skip_reddit and self.config.reddit.is_configured:
            self.fetch_reddit_upvotes()
        
        if not skip_wordpress and self.config.wordpress.is_configured:
            self.fetch_wordpress_posts()
        
        if self.config.twitter.is_configured:
            self.fetch_twitter_tweets()
        
        if not self.reddit_upvotes and not self.wordpress_posts and not self.twitter_tweets:
            console.print("\n[yellow]No content found to process.[/yellow]")
            self.logger.warning("No content found to process")
            return False
        
        if use_async:
            asyncio.run(self.generate_suggestions_async())
        else:
            self.generate_suggestions()
        
        self.display_suggestions()
        
        # Don't send email if no suggestions were generated
        total_suggestions = len(self.suggestions['reddit']) + len(self.suggestions['wordpress']) + len(self.suggestions['twitter'])
        if total_suggestions == 0:
            console.print("\n[yellow]⚠[/yellow] No suggestions generated. Skipping email send.")
            self.logger.warning("No suggestions generated. Skipping email.")
        elif not self.config.bot.dry_run and self.config.email.is_configured:
            self.send_email()
        
        console.print(Panel.fit(
            f"[bold green]✓ Workflow Complete![/bold green]\n\n"
            f"Reddit upvotes: {len(self.reddit_upvotes)}\n"
            f"WordPress posts: {len(self.wordpress_posts)}\n"
            f"My tweets: {len(self.twitter_tweets)}\n"
            f"Total suggestions: {total_suggestions}",
            border_style="green",
        ))
        
        self.logger.info("Social Content Bot workflow completed successfully")
        
        return True


def main():
    parser = argparse.ArgumentParser(
        description='Social Content Bot - Generate social media post suggestions from your content',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py
  python main.py --skip-wordpress
  python main.py --reddit-limit 20 --wordpress-limit 10 --language en
  python main.py --dry-run
  python main.py --output results.json
        """
    )
    
    parser.add_argument('--reddit-limit', type=int, help='Maximum number of Reddit upvotes to fetch')
    parser.add_argument('--posts-per-item', type=int, help='Number of post suggestions per content item')
    parser.add_argument('--language', type=str, help='Language for generated content')
    parser.add_argument('--skip-reddit', action='store_true', help='Skip fetching Reddit upvotes')
    parser.add_argument('--skip-wordpress', action='store_true', help='Skip fetching WordPress posts')
    parser.add_argument('--dry-run', action='store_true', help='Run without sending email')
    parser.add_argument('--output', '-o', type=str, help='Save results to JSON file')
    parser.add_argument('--env-file', type=str, default='.env', help='Path to environment file')
    parser.add_argument('--sync', action='store_true', help='Use synchronous API calls instead of async')
    parser.add_argument('--log-level', type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], help='Logging level')
    parser.add_argument('--debug', action='store_true', help='Test service connections and show status')
    
    args = parser.parse_args()
    
    load_dotenv(args.env_file)
    
    setup_logging(log_level=args.log_level)
    logger = get_logger()
    
    config = Config.from_env(args.env_file)
    
    if args.reddit_limit is not None:
        config.bot.reddit_limit = args.reddit_limit
    if args.posts_per_item is not None:
        config.bot.posts_per_platform = args.posts_per_item
    if args.language is not None:
        config.bot.language = args.language
    if args.dry_run:
        config.bot.dry_run = True
    
    if args.skip_reddit:
        config.bot.skip_reddit = True
    if args.skip_wordpress:
        config.bot.skip_wordpress = True
    
    issues = Config.validate(config)
    if issues and not config.bot.dry_run:
        console.print("[yellow]Configuration warnings:[/yellow]")
        for issue in issues:
            console.print(f"  - {issue}")
    
    reset_config()
    config = get_config()
    
    config.bot.reddit_limit = args.reddit_limit or config.bot.reddit_limit
    if args.posts_per_item is not None:
        # CLI arg overrides env vars for both platforms
        config.bot.twitter_alternatives = args.posts_per_item
        config.bot.linkedin_alternatives = args.posts_per_item
    config.bot.language = args.language or config.bot.language
    config.bot.dry_run = args.dry_run or config.bot.dry_run
    
    bot = SocialContentBot(config)
    
    # Debug mode - test connections
    if args.debug:
        bot.test_connections()
        return 0
    
    success = bot.run(
        skip_reddit=args.skip_reddit,
        skip_wordpress=args.skip_wordpress,
        use_async=not args.sync,
    )
    
    if args.output and success:
        bot.save_to_json(args.output)
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())