import os
import json
import asyncio
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum

import requests

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import get_config, DEFAULT_OPENAI_TEMPERATURE, DEFAULT_OPENAI_MAX_TOKENS
from utils import get_logger, retry_with_backoff, gather_with_concurrency, RateLimiter

console = Console()


class SocialPlatform(Enum):
    TWITTER = "twitter"
    LINKEDIN = "linkedin"


@dataclass
class SocialPostSuggestion:
    platform: SocialPlatform
    content: str
    hashtags: List[str]
    tone: str
    engagement_tip: str
    source_title: str = ""
    source_url: str = ""
    
    def to_dict(self) -> Dict:
        return {
            'platform': self.platform.value,
            'content': self.content,
            'hashtags': self.hashtags,
            'tone': self.tone,
            'engagement_tip': self.engagement_tip,
            'source_title': self.source_title,
            'source_url': self.source_url,
        }
    
    def format_for_display(self) -> str:
        platform_emoji = {SocialPlatform.TWITTER: "🐦", SocialPlatform.LINKEDIN: "💼"}.get(self.platform, "📱")
        hashtag_str = " ".join(f"#{tag}" for tag in self.hashtags)
        
        return f"""
{platform_emoji} {self.platform.value.upper()} Post
{'─' * 40}
{self.content}

{hashtag_str}
{'─' * 40}
Tone: {self.tone}
Tip: {self.engagement_tip}
"""


@dataclass
class ContentItem:
    source_type: str
    title: str
    url: str
    summary: str
    metadata: Dict


class ContentGenerator:
    TWITTER_SYSTEM_PROMPT = """You are an expert social media content creator specializing in Twitter/X.
Create engaging, concise tweets that capture attention and drive engagement.

CRITICAL INSTRUCTIONS:
- Return ONLY valid JSON - no markdown, no explanations, no extra text
- Use double quotes for all strings (escape internal quotes properly)
- Do NOT use code blocks (no ```json or ```)
- Return empty array if you cannot generate posts
- EACH POST MUST INCLUDE THE SOURCE URL/LINK

Output format: {"posts": [{"content": "string with link", "hashtags": ["tag1", "tag2"], "tone": "string", "engagement_tip": "string"}]}

Rules:
- Maximum 280 characters per tweet (excluding hashtags)
- Use a conversational, authentic tone
- Include a clear hook or value proposition
- Add 2-3 relevant hashtags (without # symbol in the array)
- ALWAYS include the source URL in the tweet content
- Avoid clickbait or misleading content"""

    LINKEDIN_SYSTEM_PROMPT = """You are an expert LinkedIn content creator.
Create professional, engaging LinkedIn posts that build thought leadership and drive meaningful engagement.

CRITICAL INSTRUCTIONS:
- Return ONLY valid JSON - no markdown, no explanations, no extra text
- Use double quotes for all strings (escape internal quotes properly)
- Do NOT use code blocks (no ```json or ```)
- Return empty array if you cannot generate posts
- EACH POST MUST INCLUDE THE SOURCE URL/LINK

Output format: {"posts": [{"content": "string with link", "hashtags": ["tag1", "tag2"], "tone": "string", "engagement_tip": "string"}]}

Rules:
- Start with a compelling hook (first line is crucial)
- Use short paragraphs (1-2 sentences each)
- Present the content objectively without adding personal opinions
- Add a call-to-action or question for engagement
- Use 3-5 relevant hashtags at the end (without # symbol in the array)
- ALWAYS include the source URL in the post content
- Keep it authentic and professional
- Aim for 150-300 words for optimal engagement"""

    def __init__(self, api_key: str = None, api_base: str = None, model: str = None, language: str = None):
        cfg = get_config()
        self.api_key = api_key or cfg.openai.api_key
        self.api_base = api_base or cfg.openai.api_base
        self.model = model or cfg.openai.model
        self.language = language or cfg.bot.language
        self.temperature = DEFAULT_OPENAI_TEMPERATURE
        self.max_tokens = DEFAULT_OPENAI_MAX_TOKENS
        self.timeout = cfg.bot.request_timeout
        self.max_concurrent = cfg.bot.max_concurrent_requests
        self.logger = get_logger()
        
        # Env var prompts override hardcoded defaults if set
        self.twitter_prompt = cfg.bot.twitter_prompt or self.TWITTER_SYSTEM_PROMPT
        self.linkedin_prompt = cfg.bot.linkedin_prompt or self.LINKEDIN_SYSTEM_PROMPT
        
        if not self.api_key:
            console.print("[yellow]⚠[/yellow] No API key configured. Set OPENAI_API_KEY environment variable.")
        else:
            console.print(f"\n[green]✓[/green] Content generator initialized (model: {self.model}, language: {self.language})")

    @retry_with_backoff(exceptions=(requests.RequestException,))
    def _call_ai_api(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            raise ValueError("API key not configured. Set OPENAI_API_KEY environment variable.")
        
        api_url = f"{self.api_base}/chat/completions"
        self.logger.debug(f"🌐 AI API URL: {api_url}")
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }
        
        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ],
            'temperature': self.temperature,
        }
        
        self.logger.debug(f"📤 Sending request to AI API...")
        response = requests.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=self.timeout,
        )
        
        try:
            response.raise_for_status()
            return response.json()['choices'][0]['message']['content']
        except requests.exceptions.HTTPError as e:
            self.logger.error(f"❌ HTTP error from AI API: {e}")
            self.logger.error(f"🌐 URL: {api_url}")
            if hasattr(e, 'response') and e.response is not None:
                self.logger.error(f"📄 Response: {e.response.text[:500]}")
            raise

    def _build_user_prompt(self, content_item: ContentItem, posts_per_platform: int) -> str:
        if content_item.source_type == 'my_blog':
            source_label = "MY OWN BLOG POST"
        elif content_item.source_type == 'my_tweets':
            source_label = "MY OWN RECENT TWEETS"
        elif content_item.source_type == 'reddit':
            source_label = "MY REDDIT UPVOTED POSTS (posts I upvoted on Reddit)"
        else:
            source_label = content_item.source_type.upper()
        
        return f"""Create {posts_per_platform} social media post variations based on this content:

Source: {source_label}
Title: {content_item.title}
URL: {content_item.url}

Summary:
{content_item.summary}

Additional Context:
{json.dumps(content_item.metadata, indent=2)}

IMPORTANT: Generate the posts in {self.language.upper()} language.

For each post, provide:
1. The post content (adapted for the platform)
2. 3-5 relevant hashtags (without the # symbol in the list)
3. The tone used (e.g., professional, casual, informative, provocative)
4. A tip for maximizing engagement

Format your response as JSON:
{{
  "posts": [
    {{
      "content": "The post text...",
      "hashtags": ["tag1", "tag2", "tag3"],
      "tone": "The tone used",
      "engagement_tip": "A specific tip for this post"
    }}
  ]
}}"""

    def generate_posts(self, content_item: ContentItem, platforms: List[SocialPlatform] = None, posts_per_platform: int = 2, platform_counts: Dict[SocialPlatform, int] = None) -> List[SocialPostSuggestion]:
        if platforms is None:
            platforms = [SocialPlatform.TWITTER, SocialPlatform.LINKEDIN]
        
        suggestions = []
        
        for platform in platforms:
            # Determine count for this platform: platform_counts > posts_per_platform
            count = platform_counts.get(platform, posts_per_platform) if platform_counts else posts_per_platform
            
            system_prompt = self.TWITTER_SYSTEM_PROMPT if platform == SocialPlatform.TWITTER else self.LINKEDIN_SYSTEM_PROMPT
            user_prompt = self._build_user_prompt(content_item, count)
            
            console.print(f"[dim]Generating {count} {platform.value} post variations...[/dim]")
            
            try:
                response = self._call_ai_api(system_prompt, user_prompt)
                
                if not response:
                    self.logger.error(f"❌ AI returned empty/None response for {platform.value}")
                    console.print(f"[yellow]⚠[/yellow] AI returned empty response for {platform.value}")
                    continue
                    
                response = response.strip()
                
                if response.startswith('```'):
                    response = response.split('\n', 1)[1]
                if response.endswith('```'):
                    response = response.rsplit('\n', 1)[0]
                response = response.strip()
                
                if not response:
                    self.logger.error(f"❌ AI returned empty JSON for {platform.value}")
                    console.print(f"[yellow]⚠[/yellow] AI returned empty JSON for {platform.value}")
                    continue
                
                self.logger.info(f"AI response length: {len(response)} chars")
                data = json.loads(response)
                
                for post_data in data.get('posts', []):
                    suggestion = SocialPostSuggestion(
                        platform=platform,
                        content=post_data.get('content', ''),
                        hashtags=post_data.get('hashtags', []),
                        tone=post_data.get('tone', 'professional'),
                        engagement_tip=post_data.get('engagement_tip', ''),
                        source_title=content_item.title,
                        source_url=content_item.url,
                    )
                    suggestions.append(suggestion)
                    
            except json.JSONDecodeError as e:
                self.logger.error(f"❌ JSON parsing error for {platform.value}: {e}")
                self.logger.error(f"📄 Raw AI response (first 1000 chars):\n{response[:1000]}")
                console.print(f"[yellow]⚠[/yellow] Invalid JSON from AI for {platform.value}")
                console.print(f"[dim]Response: {response[:200]}...[/dim]")
            except Exception as e:
                self.logger.error(f"❌ Error generating {platform.value} posts: {e}")
                console.print(f"[red]✗[/red] Error generating {platform.value} posts: {e}")
        
        return suggestions

    def generate_from_reddit_upvote(self, upvote_data: Dict, posts_per_platform: int = 2) -> List[SocialPostSuggestion]:
        content_item = ContentItem(
            source_type='reddit',
            title=upvote_data.get('title', ''),
            url=upvote_data.get('permalink', upvote_data.get('url', '')),
            summary=upvote_data.get('selftext', '')[:500] or f"From r/{upvote_data.get('subreddit', 'unknown')}",
            metadata={
                'subreddit': upvote_data.get('subreddit', ''),
                'author': upvote_data.get('author', ''),
                'score': upvote_data.get('score', 0),
            }
        )
        
        return self.generate_posts(content_item, platforms=[SocialPlatform.TWITTER], posts_per_platform=posts_per_platform)

    def generate_from_wordpress_post(self, post_data: Dict, posts_per_platform: int = 2) -> List[SocialPostSuggestion]:
        content_item = ContentItem(
            source_type='my_blog',
            title=post_data.get('title', ''),
            url=post_data.get('url', ''),
            summary=post_data.get('excerpt', '') or post_data.get('content', '')[:500],
            metadata={
                'author': post_data.get('author', ''),
                'categories': post_data.get('categories', []),
                'tags': post_data.get('tags', []),
                'reading_time': post_data.get('reading_time_minutes', 0),
            }
        )
        
        return self.generate_posts(content_item, platforms=[SocialPlatform.LINKEDIN], posts_per_platform=posts_per_platform)

    async def generate_posts_async(self, content_item: ContentItem, platforms: List[SocialPlatform] = None, posts_per_platform: int = 2) -> List[SocialPostSuggestion]:
        if platforms is None:
            platforms = [SocialPlatform.TWITTER, SocialPlatform.LINKEDIN]
        
        suggestions = []
        tasks = []
        
        for platform in platforms:
            system_prompt = self.TWITTER_SYSTEM_PROMPT if platform == SocialPlatform.TWITTER else self.LINKEDIN_SYSTEM_PROMPT
            user_prompt = self._build_user_prompt(content_item, posts_per_platform)
            
            async def generate_for_platform(p: SocialPlatform, sys_p: str, usr_p: str) -> List[SocialPostSuggestion]:
                self.logger.debug(f"Generating posts for {p.value}")
                return await asyncio.to_thread(self._call_ai_api, sys_p, usr_p)
            
            tasks.append((platform, generate_for_platform(platform, system_prompt, user_prompt)))
        
        results = await gather_with_concurrency(self.max_concurrent, *(t[1] for t in tasks))
        
        for i, (platform, _) in enumerate(tasks):
            try:
                response = results[i]
                if not response:
                    self.logger.error(f"❌ AI returned empty/None response for {platform.value}")
                    continue
                    
                response = response.strip()
                if response.startswith('```'):
                    response = response.split('\n', 1)[1]
                if response.endswith('```'):
                    response = response.rsplit('\n', 1)[0]
                response = response.strip()
                
                if not response:
                    self.logger.error(f"❌ AI returned empty JSON for {platform.value}")
                    continue
                
                data = json.loads(response)
                
                for post_data in data.get('posts', []):
                    suggestion = SocialPostSuggestion(
                        platform=platform,
                        content=post_data.get('content', ''),
                        hashtags=post_data.get('hashtags', []),
                        tone=post_data.get('tone', 'professional'),
                        engagement_tip=post_data.get('engagement_tip', ''),
                        source_title=content_item.title,
                        source_url=content_item.url,
                    )
                    suggestions.append(suggestion)
            except json.JSONDecodeError as e:
                self.logger.error(f"❌ JSON parsing error for {platform.value}: {e}")
                self.logger.error(f"📄 Raw AI response (first 1000 chars):\n{response[:1000]}")
            except Exception as e:
                self.logger.error(f"❌ Error parsing response for {platform.value}: {e}")
        
        return suggestions

    async def generate_from_reddit_upvote_async(self, upvote_data: Dict, posts_per_platform: int = 2) -> List[SocialPostSuggestion]:
        content_item = ContentItem(
            source_type='reddit',
            title=upvote_data.get('title', ''),
            url=upvote_data.get('permalink', upvote_data.get('url', '')),
            summary=upvote_data.get('selftext', '')[:500] or f"From r/{upvote_data.get('subreddit', 'unknown')}",
            metadata={
                'subreddit': upvote_data.get('subreddit', ''),
                'author': upvote_data.get('author', ''),
                'score': upvote_data.get('score', 0),
            }
        )
        
        return await self.generate_posts_async(content_item, posts_per_platform=posts_per_platform)

    async def generate_from_wordpress_post_async(self, post_data: Dict, posts_per_platform: int = 2) -> List[SocialPostSuggestion]:
        content_item = ContentItem(
            source_type='my_blog',
            title=post_data.get('title', ''),
            url=post_data.get('url', ''),
            summary=post_data.get('excerpt', '') or post_data.get('content', '')[:500],
            metadata={
                'author': post_data.get('author', ''),
                'categories': post_data.get('categories', []),
                'tags': post_data.get('tags', []),
                'reading_time': post_data.get('reading_time_minutes', 0),
            }
        )
        
        return await self.generate_posts_async(content_item, posts_per_platform=posts_per_platform)

    def generate_from_tweet(self, tweet_data: Dict, posts_per_platform: int = 2) -> List[SocialPostSuggestion]:
        """Generate LinkedIn posts from a tweet."""
        content_item = ContentItem(
            source_type='my_tweets',
            title=f"Tweet: {tweet_data.get('text', '')[:80]}",
            url=tweet_data.get('url', ''),
            summary=tweet_data.get('text', ''),
            metadata={
                'likes': tweet_data.get('likes', 0),
                'retweets': tweet_data.get('retweets', 0),
                'replies': tweet_data.get('replies', 0),
            }
        )
        
        return self.generate_posts(content_item, platforms=[SocialPlatform.LINKEDIN], posts_per_platform=posts_per_platform)

    async def generate_from_tweet_async(self, tweet_data: Dict, posts_per_platform: int = 2) -> List[SocialPostSuggestion]:
        """Generate LinkedIn posts from a tweet (async)."""
        content_item = ContentItem(
            source_type='my_tweets',
            title=f"Tweet: {tweet_data.get('text', '')[:80]}",
            url=tweet_data.get('url', ''),
            summary=tweet_data.get('text', ''),
            metadata={
                'likes': tweet_data.get('likes', 0),
                'retweets': tweet_data.get('retweets', 0),
                'replies': tweet_data.get('replies', 0),
            }
        )
        
        return await self.generate_posts_async(content_item, platforms=[SocialPlatform.LINKEDIN], posts_per_platform=posts_per_platform)


def display_suggestions(suggestions: List[SocialPostSuggestion]):
    for suggestion in suggestions:
        panel = Panel(
            suggestion.format_for_display(),
            title=f"[bold]{suggestion.platform.value.upper()} Post Suggestion[/bold]",
            border_style="blue",
        )
        console.print(panel)
