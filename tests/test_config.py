import os
import pytest
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config, RedditConfig, WordPressConfig, OpenAIConfig, EmailConfig, BotConfig


class TestRedditConfig:
    def test_default_values(self):
        config = RedditConfig()
        assert config.client_id == ""
        assert config.client_secret == ""
        assert config.username == ""
    
    def test_is_configured_false_when_empty(self):
        config = RedditConfig()
        assert config.is_configured is False
    
    def test_is_configured_true_when_complete(self):
        config = RedditConfig(client_id="test", client_secret="secret", username="user")
        assert config.is_configured is True


class TestWordPressConfig:
    def test_default_values(self):
        config = WordPressConfig()
        assert config.site_url == ""
    
    def test_is_configured_true_with_url(self):
        config = WordPressConfig(site_url="https://example.com")
        assert config.is_configured is True


class TestOpenAIConfig:
    def test_default_model(self):
        config = OpenAIConfig()
        assert config.model == "gpt-4"
    
    def test_is_configured_true_with_key(self):
        config = OpenAIConfig(api_key="sk-test")
        assert config.is_configured is True


class TestEmailConfig:
    def test_is_configured_true_when_complete(self):
        config = EmailConfig(
            smtp_username="user",
            smtp_password="pass",
            email_to="to@test.com"
        )
        assert config.is_configured is True


class TestBotConfig:
    def test_default_limits(self):
        config = BotConfig()
        assert config.reddit_limit == 10
        assert config.wordpress_limit == 5
        assert config.posts_per_item == 2
    
    def test_custom_limits(self):
        config = BotConfig(reddit_limit=20, wordpress_limit=10, posts_per_item=3)
        assert config.reddit_limit == 20
        assert config.wordpress_limit == 10
        assert config.posts_per_item == 3