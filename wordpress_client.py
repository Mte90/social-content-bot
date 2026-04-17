import os
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import get_config, READING_SPEED_WPM, CONTENT_PREVIEW_CHARS, WORDPRESS_CONTENT_PREVIEW_CHARS
from utils import get_logger, retry_with_backoff, create_session_with_retries

console = Console()


@dataclass
class WordPressPost:
    id: int
    title: str
    url: str
    excerpt: str
    content: str
    author: str
    published_date: datetime
    modified_date: datetime
    categories: List[str]
    tags: List[str]
    featured_image_url: Optional[str]
    reading_time_minutes: int
    
    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'title': self.title,
            'url': self.url,
            'excerpt': self.excerpt,
            'content': self.content[:WORDPRESS_CONTENT_PREVIEW_CHARS],
            'author': self.author,
            'published_date': self.published_date.isoformat(),
            'modified_date': self.modified_date.isoformat(),
            'categories': self.categories,
            'tags': self.tags,
            'featured_image_url': self.featured_image_url,
            'reading_time_minutes': self.reading_time_minutes,
        }


class WordPressClient:
    def __init__(self, site_url: str = None, username: str = None, password: str = None):
        cfg = get_config()
        self.site_url = (site_url or cfg.wordpress.site_url or '').rstrip('/')
        self.username = username or cfg.wordpress.username
        # Remove spaces from app password (WordPress adds spaces for readability)
        self.password = (password or cfg.wordpress.app_password or '').replace(' ', '')
        self.logger = get_logger()
        
        if not self.site_url:
            raise ValueError(
                "WordPress site URL not configured. Set WORDPRESS_SITE_URL environment variable."
            )
        
        self.api_url = f"{self.site_url}/wp-json/wp/v2"
        
        self.auth = None
        if self.username and self.password:
            self.auth = (self.username, self.password)
            console.print(f"[green]✓[/green] WordPress client initialized with authentication")
        else:
            console.print(f"[yellow]⚠[/yellow] WordPress client initialized without authentication (public posts only)")
        
        self.session = create_session_with_retries()
        # Add User-Agent header to avoid being blocked by WordPress/firewall
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self._verify_api_access()

    def _verify_api_access(self) -> bool:
        try:
            response = self.session.get(f"{self.api_url}/posts", params={'per_page': 1}, auth=self.auth)
            response.raise_for_status()
            self.logger.info(f"WordPress REST API accessible at {self.site_url}")
            console.print(f"[green]✓[/green] WordPress REST API accessible at {self.site_url}")
            return True
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Could not access WordPress REST API: {e}")
            console.print(f"[red]✗[/red] Could not access WordPress REST API: {e}")
            return False

    @retry_with_backoff(exceptions=(requests.exceptions.RequestException,))
    def get_posts(self, days: int = 7, author_id: int = None, categories: List[int] = None, tags: List[int] = None, search: str = None) -> List[WordPressPost]:
        posts = []
        
        console.print(f"\n[bold blue]Fetching WordPress posts from last {days} days...[/bold blue]")
        
        params = {
            'per_page': 100,
            '_embed': 'true',
            'orderby': 'date',
            'order': 'desc',
        }
        
        if days and days > 0:
            from datetime import timedelta, timezone
            after_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            params['after'] = after_date
        
        if author_id:
            params['author'] = author_id
        if categories:
            params['categories'] = ','.join(map(str, categories))
        if tags:
            params['tags'] = ','.join(map(str, tags))
        if search:
            params['search'] = search
        
        try:
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
                task = progress.add_task("Downloading posts...", total=None)
                
                response = self.session.get(f"{self.api_url}/posts", params=params, auth=self.auth)
                response.raise_for_status()
                
                posts_data = response.json()
                total_posts = response.headers.get('X-WP-Total', len(posts_data))
                progress.update(task, description=f"Found {total_posts} posts, processing...")
                
                for post_data in posts_data:
                    post = self._parse_post(post_data)
                    posts.append(post)
            
            self.logger.info(f"Successfully fetched {len(posts)} posts")
            console.print(f"[green]✓[/green] Successfully fetched {len(posts)} posts")
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching WordPress posts: {e}")
            console.print(f"[red]✗[/red] Error fetching WordPress posts: {e}")
            raise
        
        return posts

    def _parse_post(self, post_data: Dict) -> WordPressPost:
        embedded = post_data.get('_embedded', {})
        
        author_data = embedded.get('author', [{}])
        author = author_data[0].get('name', 'Unknown') if author_data else 'Unknown'
        
        categories_data = embedded.get('wp:term', [[]])
        categories = []
        if categories_data and len(categories_data) > 0:
            categories = [cat.get('name', '') for cat in categories_data[0] if cat.get('taxonomy') == 'category']
        
        tags = []
        if categories_data and len(categories_data) > 1:
            tags = [tag.get('name', '') for tag in categories_data[1] if tag.get('taxonomy') == 'post_tag']
        
        featured_image_url = None
        if 'wp:featuredmedia' in embedded:
            media = embedded['wp:featuredmedia']
            if media and len(media) > 0:
                featured_image_url = media[0].get('source_url')
        
        content = post_data.get('content', {}).get('rendered', '')
        text_content = self._strip_html(content)
        word_count = len(text_content.split())
        reading_time = max(1, round(word_count / READING_SPEED_WPM))
        
        return WordPressPost(
            id=post_data['id'],
            title=self._strip_html(post_data.get('title', {}).get('rendered', '')),
            url=post_data.get('link', ''),
            excerpt=self._strip_html(post_data.get('excerpt', {}).get('rendered', '')),
            content=text_content,
            author=author,
            published_date=datetime.fromisoformat(post_data['date'].replace('Z', '+00:00')),
            modified_date=datetime.fromisoformat(post_data['modified'].replace('Z', '+00:00')),
            categories=categories,
            tags=tags,
            featured_image_url=featured_image_url,
            reading_time_minutes=reading_time,
        )

    def _strip_html(self, html: str) -> str:
        if not html:
            return ''
        soup = BeautifulSoup(html, 'lxml')
        return soup.get_text(separator=' ', strip=True)

    def format_post_for_content(self, post: WordPressPost) -> str:
        content = f"""Title: {post.title}
Author: {post.author}
Published: {post.published_date.strftime('%Y-%m-%d')}
URL: {post.url}
Reading Time: {post.reading_time_minutes} min
Categories: {', '.join(post.categories) if post.categories else 'None'}
Tags: {', '.join(post.tags) if post.tags else 'None'}

Excerpt:
{post.excerpt}

Content Preview:
{post.content[:800]}...
"""
        return content

    def get_recent_posts(self, days: int = 30, limit: int = 10) -> List[WordPressPost]:
        from datetime import timedelta, timezone
        
        after_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        params = {
            'per_page': limit,
            'after': after_date,
            '_embed': 'true',
            'orderby': 'date',
            'order': 'desc',
        }
        
        try:
            response = self.session.get(f"{self.api_url}/posts", params=params, auth=self.auth)
            response.raise_for_status()
            
            posts = [self._parse_post(p) for p in response.json()]
            self.logger.info(f"Found {len(posts)} posts from the last {days} days")
            console.print(f"[green]✓[/green] Found {len(posts)} posts from the last {days} days")
            return posts
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error fetching recent posts: {e}")
            console.print(f"[red]✗[/red] Error fetching recent posts: {e}")
            raise