# -*- coding: utf-8 -*-
"""
Google Gemini Client for OCR Extraction.
לקוח Google Gemini לחילוץ נתונים מ-OCR

This module provides a dedicated client for Google Gemini Flash
with rate limiting and error handling for the free tier.

Free Tier Limits (as of 2025):
- 15 requests per minute
- 1 million tokens per day
- 1,500 requests per day
"""

import os
import time
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from threading import Lock

logger = logging.getLogger(__name__)


@dataclass
class GeminiConfig:
    """Configuration for Gemini client."""
    api_key: Optional[str] = None
    model: str = "gemini-2.0-flash-lite"
    requests_per_minute: int = 15
    daily_token_limit: int = 1_000_000
    daily_request_limit: int = 1_500
    temperature: float = 0.1
    max_output_tokens: int = 500
    timeout: int = 30


@dataclass
class UsageStats:
    """Track API usage for rate limiting."""
    requests_this_minute: int = 0
    minute_start: float = 0.0
    tokens_today: int = 0
    requests_today: int = 0
    day_start: str = ""

    def reset_minute(self):
        self.requests_this_minute = 0
        self.minute_start = time.time()

    def reset_day(self):
        self.tokens_today = 0
        self.requests_today = 0
        self.day_start = datetime.now().strftime("%Y-%m-%d")


class GeminiClient:
    """
    Client for Google Gemini API with rate limiting.

    Manages API calls, rate limiting, and error handling
    for the free tier of Google Gemini.
    """

    def __init__(self, config: Optional[GeminiConfig] = None):
        """
        Initialize the Gemini client.

        Args:
            config: Configuration for the client
        """
        self.config = config or GeminiConfig()

        # Get API key from config or environment
        self.api_key = (
            self.config.api_key or
            os.environ.get('GEMINI_API_KEY') or
            os.environ.get('GOOGLE_API_KEY')
        )

        self._client = None
        self._available: Optional[bool] = None
        self._usage = UsageStats()
        self._lock = Lock()

    def is_available(self) -> bool:
        """Check if Gemini client is available and configured."""
        if self._available is not None:
            return self._available

        if not self.api_key:
            logger.info("Gemini API key not configured")
            self._available = False
            return False

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._client = genai.GenerativeModel(self.config.model)

            # Test with a simple request
            # Note: This counts against rate limits
            # response = self._client.generate_content("Hi")

            self._available = True
            logger.info(f"Gemini client initialized with model: {self.config.model}")

        except ImportError:
            logger.warning("google-generativeai package not installed")
            self._available = False
        except Exception as e:
            logger.warning(f"Failed to initialize Gemini: {e}")
            self._available = False

        return self._available

    def _check_rate_limits(self) -> tuple:
        """
        Check if we're within rate limits.

        Returns:
            Tuple of (can_proceed, wait_time, reason)
        """
        current_time = time.time()
        today = datetime.now().strftime("%Y-%m-%d")

        # Check if day has changed
        if self._usage.day_start != today:
            self._usage.reset_day()

        # Check daily limits
        if self._usage.requests_today >= self.config.daily_request_limit:
            return False, 0, "Daily request limit reached"

        if self._usage.tokens_today >= self.config.daily_token_limit:
            return False, 0, "Daily token limit reached"

        # Check minute limits
        elapsed = current_time - self._usage.minute_start

        if elapsed >= 60:
            self._usage.reset_minute()
        elif self._usage.requests_this_minute >= self.config.requests_per_minute:
            wait_time = 60 - elapsed
            return False, wait_time, f"Rate limit: wait {wait_time:.1f}s"

        return True, 0, None

    def _wait_for_rate_limit(self, max_wait: float = 60.0) -> bool:
        """
        Wait if rate limited.

        Returns:
            True if can proceed, False if should abort
        """
        can_proceed, wait_time, reason = self._check_rate_limits()

        if can_proceed:
            return True

        if wait_time > 0 and wait_time <= max_wait:
            logger.debug(f"Rate limited, waiting {wait_time:.1f}s")
            time.sleep(wait_time)
            return True

        logger.warning(f"Rate limit: {reason}")
        return False

    def _update_usage(self, tokens_used: int = 0):
        """Update usage statistics after a request."""
        with self._lock:
            self._usage.requests_this_minute += 1
            self._usage.requests_today += 1
            self._usage.tokens_today += tokens_used

    def generate(
        self,
        prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> Optional[str]:
        """
        Generate text using Gemini.

        Args:
            prompt: The prompt to send
            temperature: Override default temperature
            max_tokens: Override default max tokens

        Returns:
            Generated text or None if failed
        """
        if not self.is_available():
            return None

        if not self._wait_for_rate_limit():
            return None

        try:
            response = self._client.generate_content(
                prompt,
                generation_config={
                    'temperature': temperature or self.config.temperature,
                    'max_output_tokens': max_tokens or self.config.max_output_tokens,
                }
            )

            # Estimate tokens (rough approximation)
            tokens_used = len(prompt.split()) + len(response.text.split()) * 2
            self._update_usage(tokens_used)

            return response.text

        except Exception as e:
            logger.error(f"Gemini generation error: {e}")
            return None

    def extract_vote(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extract vote information from Hebrew text.

        Args:
            text: Text containing voting information

        Returns:
            Dict with vote data or None
        """
        prompt = f"""Extract voting results from this Hebrew municipal protocol text.
Return ONLY a JSON object with this structure:
{{"type": "unanimous" | "counted", "yes": number, "no": number, "abstain": number}}

For unanimous votes (פה אחד), set type to "unanimous" and counts to 0.
Note: Text may be reversed (RTL read as LTR).

Text:
{text[:1500]}

JSON:"""

        response = self.generate(prompt)
        if not response:
            return None

        return self._parse_json_response(response)

    def extract_decision(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extract decision information from Hebrew text.

        Args:
            text: Text containing decision information

        Returns:
            Dict with decision data or None
        """
        prompt = f"""Extract the decision from this Hebrew municipal protocol text.
Return ONLY a JSON object with this structure:
{{"status": "אושר" | "נדחה" | "לידיעה", "text": "decision text in Hebrew"}}

Common statuses:
- אושר = approved
- נדחה = rejected
- לידיעה = for information only

Text:
{text[:1500]}

JSON:"""

        response = self.generate(prompt)
        if not response:
            return None

        return self._parse_json_response(response)

    def extract_attendees(self, text: str) -> Optional[List[Dict[str, str]]]:
        """
        Extract attendees list from Hebrew text.

        Args:
            text: Text containing attendee information

        Returns:
            List of attendee dicts or None
        """
        prompt = f"""Extract the list of attendees from this Hebrew text.
Return ONLY a JSON array of objects:
[{{"name": "Hebrew name", "role": "role if mentioned"}}]

Note: Text may be reversed. Look for Hebrew names.

Text:
{text[:2000]}

JSON:"""

        response = self.generate(prompt)
        if not response:
            return None

        result = self._parse_json_response(response)
        if isinstance(result, list):
            return result
        return None

    def match_names(
        self,
        ocr_name: str,
        candidates: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Match an OCR-extracted name to a list of candidates.

        Args:
            ocr_name: The name from OCR (may be reversed/corrupted)
            candidates: List of correct names to match against

        Returns:
            Dict with match result or None
        """
        if not candidates:
            return None

        candidates_str = "\n".join(f"- {c}" for c in candidates[:20])

        prompt = f"""Match this OCR-extracted Hebrew name to one of the candidates.
The OCR name may be reversed (RTL read as LTR) or contain errors.

OCR Name: {ocr_name}

Candidates:
{candidates_str}

If there's a match, return: {{"match": true, "name": "matching candidate name", "confidence": 0.0-1.0}}
If no match: {{"match": false}}

JSON:"""

        response = self.generate(prompt)
        if not response:
            return None

        return self._parse_json_response(response)

    def _parse_json_response(self, response: str) -> Optional[Any]:
        """Parse JSON from Gemini response."""
        if not response:
            return None

        # Try to extract JSON from response
        import re

        # Try object
        match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        # Try array
        match = re.search(r'\[[^\[\]]*\]', response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        logger.debug(f"Could not parse JSON from response: {response[:200]}")
        return None

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get current usage statistics."""
        return {
            'requests_this_minute': self._usage.requests_this_minute,
            'requests_today': self._usage.requests_today,
            'tokens_today': self._usage.tokens_today,
            'daily_request_limit': self.config.daily_request_limit,
            'daily_token_limit': self.config.daily_token_limit,
            'requests_per_minute': self.config.requests_per_minute,
        }


# Singleton instance
_client: Optional[GeminiClient] = None


def get_client(config: Optional[GeminiConfig] = None) -> GeminiClient:
    """Get or create the Gemini client singleton."""
    global _client
    if _client is None or config is not None:
        _client = GeminiClient(config)
    return _client


def is_available() -> bool:
    """Check if Gemini is available."""
    return get_client().is_available()


def extract_vote(text: str) -> Optional[Dict[str, Any]]:
    """Extract vote from text."""
    return get_client().extract_vote(text)


def extract_decision(text: str) -> Optional[Dict[str, Any]]:
    """Extract decision from text."""
    return get_client().extract_decision(text)


def extract_attendees(text: str) -> Optional[List[Dict[str, str]]]:
    """Extract attendees from text."""
    return get_client().extract_attendees(text)


def match_names(
    ocr_name: str,
    candidates: List[str]
) -> Optional[Dict[str, Any]]:
    """Match OCR name to candidates."""
    return get_client().match_names(ocr_name, candidates)


__all__ = [
    'GeminiConfig',
    'GeminiClient',
    'get_client',
    'is_available',
    'extract_vote',
    'extract_decision',
    'extract_attendees',
    'match_names',
]
