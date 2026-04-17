import os
import pytest
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import retry_with_backoff, RateLimiter, gather_with_concurrency, create_session_with_retries
import asyncio


class TestRetryWithBackoff:
    def test_successful_call(self):
        call_count = 0
        
        @retry_with_backoff(max_attempts=3, initial_delay=0.01)
        def success_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = success_func()
        assert result == "success"
        assert call_count == 1
    
    def test_retry_on_failure_then_success(self):
        call_count = 0
        
        @retry_with_backoff(max_attempts=3, initial_delay=0.01)
        def retry_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("temp error")
            return "success"
        
        result = retry_func()
        assert result == "success"
        assert call_count == 2
    
    def test_max_attempts_exceeded(self):
        call_count = 0
        
        @retry_with_backoff(max_attempts=3, initial_delay=0.01)
        def fail_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("permanent error")
        
        with pytest.raises(ValueError):
            fail_func()
        
        assert call_count == 3


class TestRateLimiter:
    def test_acquire_sync(self):
        limiter = RateLimiter(calls_per_second=10)
        limiter.last_call = 0
        limiter.acquire_sync()
        assert limiter.last_call > 0


class TestGatherWithConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_execution(self):
        results = []
        
        async def task(i):
            await asyncio.sleep(0.01)
            results.append(i)
            return i
        
        output = await gather_with_concurrency(3, task(1), task(2), task(3))
        assert sorted(output) == [1, 2, 3]


class TestCreateSessionWithRetries:
    def test_session_created(self):
        session = create_session_with_retries()
        assert session is not None
        assert hasattr(session, 'mount')