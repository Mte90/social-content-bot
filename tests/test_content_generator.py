import os
import pytest
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from content_generator import ContentGenerator, SocialPostSuggestion, SocialPlatform, ContentItem


class TestContentItem:
    def test_content_item_creation(self):
        item = ContentItem(
            source_type='reddit',
            title='Test Title',
            url='https://reddit.com/r/test',
            summary='Test summary',
            metadata={'subreddit': 'test'}
        )
        assert item.source_type == 'reddit'
        assert item.title == 'Test Title'
        assert item.metadata['subreddit'] == 'test'


class TestSocialPostSuggestion:
    def test_to_dict(self):
        suggestion = SocialPostSuggestion(
            platform=SocialPlatform.TWITTER,
            content='Test content',
            hashtags=['test', 'hashtag'],
            tone='casual',
            engagement_tip='Ask a question'
        )
        d = suggestion.to_dict()
        assert d['platform'] == 'twitter'
        assert d['content'] == 'Test content'
        assert d['hashtags'] == ['test', 'hashtag']
    
    def test_format_for_display(self):
        suggestion = SocialPostSuggestion(
            platform=SocialPlatform.TWITTER,
            content='Test content',
            hashtags=['test'],
            tone='casual',
            engagement_tip='Tip'
        )
        formatted = suggestion.format_for_display()
        assert '🐦' in formatted
        assert 'TWITTER' in formatted
        assert '#test' in formatted


class TestContentGenerator:
    @patch('content_generator.get_config')
    def test_init_without_api_key(self, mock_config):
        mock_cfg = MagicMock()
        mock_cfg.openai.api_key = ""
        mock_cfg.openai.api_base = "https://api.openai.com/v1"
        mock_cfg.openai.model = "gpt-4"
        mock_cfg.bot.language = "en"
        mock_cfg.bot.request_timeout = 60
        mock_cfg.bot.max_concurrent_requests = 5
        mock_config.return_value = mock_cfg
        
        with patch('content_generator.get_logger') as mock_logger:
            mock_logger.return_value = MagicMock()
            gen = ContentGenerator()
            assert gen.api_key == ""
    
    @patch('content_generator.get_config')
    def test_build_user_prompt(self, mock_config):
        mock_cfg = MagicMock()
        mock_cfg.openai.api_key = "test-key"
        mock_cfg.openai.api_base = "https://api.openai.com/v1"
        mock_cfg.openai.model = "gpt-4"
        mock_cfg.bot.language = "en"
        mock_cfg.bot.request_timeout = 60
        mock_cfg.bot.max_concurrent_requests = 5
        mock_config.return_value = mock_cfg
        
        with patch('content_generator.get_logger') as mock_logger:
            mock_logger.return_value = MagicMock()
            gen = ContentGenerator()
            
            item = ContentItem(
                source_type='reddit',
                title='Test Post',
                url='https://reddit.com/r/test/comments/123',
                summary='This is a test summary',
                metadata={'subreddit': 'test'}
            )
            
            prompt = gen._build_user_prompt(item, 2)
            assert 'Test Post' in prompt
            assert 'en' in prompt.upper()
            assert '2 social media post variations' in prompt