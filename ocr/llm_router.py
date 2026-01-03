# -*- coding: utf-8 -*-
"""
LLM Router for OCR Extraction.
ניתוב LLM לחילוץ נתונים מ-OCR

This module provides intelligent routing between different extraction methods:
1. Regex (fast, free, works for common patterns)
2. Ollama/Gemma3 (local, free, good for Hebrew)
3. Google Gemini Flash (free tier: 15 req/min, 1M tokens/day)

The router tries the cheapest/fastest option first and falls back
to more capable options only when needed.
"""

import re
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class ExtractionType(Enum):
    """Types of data that can be extracted."""
    HEADER = "header"
    ATTENDEES = "attendees"
    ABSENT = "absent"
    STAFF = "staff"
    DISCUSSION = "discussion"
    VOTE = "vote"
    DECISION = "decision"
    NAME_MATCH = "name_match"
    GENERAL = "general"


class ExtractionMethod(Enum):
    """Methods used for extraction."""
    REGEX = "regex"
    OLLAMA = "ollama"
    GEMINI = "gemini"
    CLAUDE = "claude"  # Future
    MANUAL = "manual"


@dataclass
class ExtractionResult:
    """Result of an extraction attempt."""
    success: bool
    data: Any = None
    confidence: float = 0.0
    method: ExtractionMethod = ExtractionMethod.REGEX
    raw_response: str = ""
    error: Optional[str] = None
    tokens_used: int = 0

    def is_good_enough(self, threshold: float = 0.7) -> bool:
        """Check if the result meets the confidence threshold."""
        return self.success and self.confidence >= threshold


@dataclass
class RouterConfig:
    """Configuration for the LLM Router."""
    # Confidence thresholds for fallback
    regex_threshold: float = 0.7
    ollama_threshold: float = 0.6

    # Enable/disable providers
    enable_ollama: bool = True
    enable_gemini: bool = True
    enable_claude: bool = False  # Future

    # Rate limiting
    gemini_requests_per_minute: int = 15
    gemini_daily_token_limit: int = 1_000_000

    # Ollama settings
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "gemma3:1b"
    ollama_timeout: int = 60

    # Gemini settings
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.0-flash-lite"


class ExtractionProvider(ABC):
    """Abstract base class for extraction providers."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is available."""
        pass

    @abstractmethod
    def extract(
        self,
        text: str,
        extraction_type: ExtractionType,
        context: Optional[Dict] = None
    ) -> ExtractionResult:
        """Perform extraction."""
        pass


class RegexProvider(ExtractionProvider):
    """Provider that uses regex patterns for extraction."""

    # Regex patterns for different extraction types
    PATTERNS = {
        ExtractionType.VOTE: {
            'unanimous': [
                r'פה\s*אחד',
                r'ללא\s+מתנגדים',
                r'אושר\s+פה\s*אחד',
            ],
            'counted': [
                r'(\d+)\s*בעד',
                r'(\d+)\s*נגד',
                r'(\d+)\s*נמנע',
            ],
        },
        ExtractionType.DECISION: {
            'approved': [r'אושר', r'התקבל', r'מאשרת'],
            'rejected': [r'נדחה', r'לא\s+אושר'],
            'info': [r'לידיעה'],
        },
        ExtractionType.HEADER: {
            'meeting_number': [r'ישיבה\s*(מס[\'׳]?)?\s*(\d+)'],
            'date': [r'(\d{1,2})[/\.\-](\d{1,2})[/\.\-](20\d{2})'],
        },
    }

    def is_available(self) -> bool:
        return True  # Regex is always available

    def extract(
        self,
        text: str,
        extraction_type: ExtractionType,
        context: Optional[Dict] = None
    ) -> ExtractionResult:
        """Extract using regex patterns."""
        if not text:
            return ExtractionResult(success=False, error="Empty text")

        patterns = self.PATTERNS.get(extraction_type, {})
        result_data = {}
        matches_found = 0
        total_patterns = 0

        for category, pattern_list in patterns.items():
            total_patterns += len(pattern_list)
            for pattern in pattern_list:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    matches_found += 1
                    result_data[category] = match.groups() if match.groups() else match.group()
                    break

        if matches_found == 0:
            return ExtractionResult(
                success=False,
                method=ExtractionMethod.REGEX,
                error="No patterns matched"
            )

        # Calculate confidence based on how many patterns matched
        confidence = matches_found / max(total_patterns, 1)

        return ExtractionResult(
            success=True,
            data=result_data,
            confidence=min(confidence + 0.3, 0.9),  # Boost but cap at 0.9
            method=ExtractionMethod.REGEX
        )


class OllamaProvider(ExtractionProvider):
    """Provider that uses local Ollama for extraction."""

    def __init__(self, config: RouterConfig):
        self.config = config
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        """Check if Ollama is running and available."""
        if self._available is not None:
            return self._available

        if not self.config.enable_ollama:
            self._available = False
            return False

        try:
            import requests
            response = requests.get(
                f"{self.config.ollama_host}/api/tags",
                timeout=5
            )
            self._available = response.status_code == 200
        except Exception:
            self._available = False

        return self._available

    def extract(
        self,
        text: str,
        extraction_type: ExtractionType,
        context: Optional[Dict] = None
    ) -> ExtractionResult:
        """Extract using Ollama."""
        if not self.is_available():
            return ExtractionResult(
                success=False,
                method=ExtractionMethod.OLLAMA,
                error="Ollama not available"
            )

        prompt = self._build_prompt(text, extraction_type, context)

        try:
            import requests
            response = requests.post(
                f"{self.config.ollama_host}/api/generate",
                json={
                    "model": self.config.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 500,
                    }
                },
                timeout=self.config.ollama_timeout
            )

            if response.status_code != 200:
                return ExtractionResult(
                    success=False,
                    method=ExtractionMethod.OLLAMA,
                    error=f"Ollama error: {response.status_code}"
                )

            result = response.json()
            raw_response = result.get('response', '')

            # Parse the response
            parsed_data, confidence = self._parse_response(
                raw_response,
                extraction_type
            )

            return ExtractionResult(
                success=True,
                data=parsed_data,
                confidence=confidence,
                method=ExtractionMethod.OLLAMA,
                raw_response=raw_response,
                tokens_used=result.get('eval_count', 0)
            )

        except Exception as e:
            logger.error(f"Ollama extraction error: {e}")
            return ExtractionResult(
                success=False,
                method=ExtractionMethod.OLLAMA,
                error=str(e)
            )

    def _build_prompt(
        self,
        text: str,
        extraction_type: ExtractionType,
        context: Optional[Dict]
    ) -> str:
        """Build the prompt for Ollama."""
        # Note: Use double braces {{}} for literal braces in f-strings
        prompts = {
            ExtractionType.VOTE: """
אנא חלץ את תוצאות ההצבעה מהטקסט הבא.
החזר JSON בפורמט: {{"type": "unanimous"|"counted", "yes": number, "no": number, "abstain": number}}

טקסט:
{text}

JSON:""",
            ExtractionType.DECISION: """
אנא חלץ את ההחלטה מהטקסט הבא.
החזר JSON בפורמט: {{"status": "אושר"|"נדחה"|"לידיעה", "text": "נוסח ההחלטה"}}

טקסט:
{text}

JSON:""",
            ExtractionType.NAME_MATCH: """
האם שני השמות הבאים מתייחסים לאותו אדם?
שם 1: {name1}
שם 2: {name2}

שים לב: הטקסט עשוי להיות הפוך (RTL שנקרא כ-LTR).
החזר: YES או NO

תשובה:""",
            ExtractionType.GENERAL: """
{prompt}

טקסט:
{text}

תשובה:""",
        }

        template = prompts.get(extraction_type, prompts[ExtractionType.GENERAL])

        # Format the template
        format_args = {'text': text[:1500]}  # Limit text length
        if context:
            format_args.update(context)

        return template.format(**format_args)

    def _parse_response(
        self,
        response: str,
        extraction_type: ExtractionType
    ) -> tuple:
        """Parse Ollama response and return (data, confidence)."""
        response = response.strip()

        # Try to extract JSON
        json_match = re.search(r'\{[^}]+\}', response)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return data, 0.75
            except json.JSONDecodeError:
                pass

        # For YES/NO responses
        if extraction_type == ExtractionType.NAME_MATCH:
            if 'YES' in response.upper():
                return {'match': True}, 0.8
            elif 'NO' in response.upper():
                return {'match': False}, 0.8

        # Return raw response with lower confidence
        return {'raw': response}, 0.5


class GeminiProvider(ExtractionProvider):
    """Provider that uses Google Gemini Flash for extraction."""

    def __init__(self, config: RouterConfig):
        self.config = config
        self._client = None
        self._available: Optional[bool] = None
        self._request_count = 0
        self._last_minute_reset = 0

    def is_available(self) -> bool:
        """Check if Gemini is available and configured."""
        if self._available is not None:
            return self._available

        if not self.config.enable_gemini:
            self._available = False
            return False

        if not self.config.gemini_api_key:
            self._available = False
            return False

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.config.gemini_api_key)
            self._client = genai.GenerativeModel(self.config.gemini_model)
            self._available = True
        except ImportError:
            logger.warning("google-generativeai not installed")
            self._available = False
        except Exception as e:
            logger.warning(f"Gemini initialization error: {e}")
            self._available = False

        return self._available

    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits."""
        import time
        current_minute = int(time.time() / 60)

        if current_minute > self._last_minute_reset:
            self._request_count = 0
            self._last_minute_reset = current_minute

        return self._request_count < self.config.gemini_requests_per_minute

    def extract(
        self,
        text: str,
        extraction_type: ExtractionType,
        context: Optional[Dict] = None
    ) -> ExtractionResult:
        """Extract using Google Gemini."""
        if not self.is_available():
            return ExtractionResult(
                success=False,
                method=ExtractionMethod.GEMINI,
                error="Gemini not available"
            )

        if not self._check_rate_limit():
            return ExtractionResult(
                success=False,
                method=ExtractionMethod.GEMINI,
                error="Rate limit exceeded"
            )

        prompt = self._build_prompt(text, extraction_type, context)

        try:
            response = self._client.generate_content(
                prompt,
                generation_config={
                    'temperature': 0.1,
                    'max_output_tokens': 500,
                }
            )

            self._request_count += 1
            raw_response = response.text

            # Parse the response
            parsed_data, confidence = self._parse_response(
                raw_response,
                extraction_type
            )

            return ExtractionResult(
                success=True,
                data=parsed_data,
                confidence=confidence,
                method=ExtractionMethod.GEMINI,
                raw_response=raw_response
            )

        except Exception as e:
            logger.error(f"Gemini extraction error: {e}")
            return ExtractionResult(
                success=False,
                method=ExtractionMethod.GEMINI,
                error=str(e)
            )

    def _build_prompt(
        self,
        text: str,
        extraction_type: ExtractionType,
        context: Optional[Dict]
    ) -> str:
        """Build the prompt for Gemini."""
        # Use similar prompts to Ollama but optimized for Gemini
        # Note: Use double braces {{}} for literal braces
        prompts = {
            ExtractionType.VOTE: """
You are analyzing a Hebrew municipal protocol. Extract the voting results.

Return ONLY a JSON object in this format:
{{"type": "unanimous" or "counted", "yes": number, "no": number, "abstain": number}}

Note: The text may be reversed (RTL read as LTR). Common patterns:
- "פה אחד" or "דחא הפ" = unanimous
- Numbers followed by "בעד"/"דעב" = yes votes
- Numbers followed by "נגד"/"דגנ" = no votes

Text:
{text}

JSON:""",
            ExtractionType.DECISION: """
You are analyzing a Hebrew municipal protocol. Extract the decision.

Return ONLY a JSON object in this format:
{{"status": "אושר" or "נדחה" or "לידיעה", "text": "decision text in Hebrew"}}

Text:
{text}

JSON:""",
            ExtractionType.NAME_MATCH: """
Determine if these two Hebrew names refer to the same person.
Consider that OCR may have reversed the text (RTL→LTR).

Name 1: {name1}
Name 2: {name2}

Answer with ONLY: YES or NO""",
            ExtractionType.ATTENDEES: """
Extract the list of attendees from this Hebrew text.
Return a JSON array of objects: [{{"name": "...", "role": "..."}}]

Text:
{text}

JSON:""",
        }

        template = prompts.get(extraction_type, """
{prompt}

Text:
{text}

Answer:""")

        format_args = {'text': text[:2000]}
        if context:
            format_args.update(context)

        return template.format(**format_args)

    def _parse_response(
        self,
        response: str,
        extraction_type: ExtractionType
    ) -> tuple:
        """Parse Gemini response."""
        response = response.strip()

        # Extract JSON
        json_patterns = [
            r'\{[^{}]*\}',
            r'\[[^\[\]]*\]',
        ]

        for pattern in json_patterns:
            match = re.search(pattern, response, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                    return data, 0.85
                except json.JSONDecodeError:
                    pass

        # YES/NO responses
        if extraction_type == ExtractionType.NAME_MATCH:
            response_upper = response.upper()
            if 'YES' in response_upper:
                return {'match': True}, 0.9
            elif 'NO' in response_upper:
                return {'match': False}, 0.9

        return {'raw': response}, 0.6


class LLMRouter:
    """
    Routes extraction requests through multiple providers.

    Strategy:
    1. Try Regex first (fast, free)
    2. If confidence < threshold, try Ollama (local, free)
    3. If still low, try Gemini Flash (free tier)
    """

    def __init__(self, config: Optional[RouterConfig] = None):
        self.config = config or RouterConfig()
        self.providers = {
            ExtractionMethod.REGEX: RegexProvider(),
            ExtractionMethod.OLLAMA: OllamaProvider(self.config),
            ExtractionMethod.GEMINI: GeminiProvider(self.config),
        }

    def extract(
        self,
        text: str,
        extraction_type: ExtractionType,
        context: Optional[Dict] = None,
        min_confidence: float = 0.6
    ) -> ExtractionResult:
        """
        Extract data using the most appropriate method.

        Args:
            text: The text to extract from
            extraction_type: What type of data to extract
            context: Additional context for the extraction
            min_confidence: Minimum confidence to accept

        Returns:
            ExtractionResult with the best result found
        """
        best_result = ExtractionResult(success=False, error="No extraction attempted")

        # 1. Try Regex first
        regex_provider = self.providers[ExtractionMethod.REGEX]
        result = regex_provider.extract(text, extraction_type, context)

        if result.is_good_enough(self.config.regex_threshold):
            logger.debug(f"Regex succeeded with confidence {result.confidence}")
            return result

        if result.success:
            best_result = result

        # 2. Try Ollama
        if self.config.enable_ollama:
            ollama_provider = self.providers[ExtractionMethod.OLLAMA]
            if ollama_provider.is_available():
                result = ollama_provider.extract(text, extraction_type, context)

                if result.is_good_enough(self.config.ollama_threshold):
                    logger.debug(f"Ollama succeeded with confidence {result.confidence}")
                    return result

                if result.success and result.confidence > best_result.confidence:
                    best_result = result

        # 3. Try Gemini
        if self.config.enable_gemini:
            gemini_provider = self.providers[ExtractionMethod.GEMINI]
            if gemini_provider.is_available():
                result = gemini_provider.extract(text, extraction_type, context)

                if result.success and result.confidence > best_result.confidence:
                    best_result = result

                if result.is_good_enough(min_confidence):
                    logger.debug(f"Gemini succeeded with confidence {result.confidence}")
                    return result

        # Return best result we have
        return best_result

    def is_ollama_available(self) -> bool:
        """Check if Ollama is available."""
        return self.providers[ExtractionMethod.OLLAMA].is_available()

    def is_gemini_available(self) -> bool:
        """Check if Gemini is available."""
        return self.providers[ExtractionMethod.GEMINI].is_available()


# Singleton instance for convenience
_router: Optional[LLMRouter] = None


def get_router(config: Optional[RouterConfig] = None) -> LLMRouter:
    """Get or create the LLM router singleton."""
    global _router
    if _router is None or config is not None:
        _router = LLMRouter(config)
    return _router


def extract(
    text: str,
    extraction_type: ExtractionType,
    context: Optional[Dict] = None
) -> ExtractionResult:
    """Convenience function for extraction."""
    router = get_router()
    return router.extract(text, extraction_type, context)


__all__ = [
    'ExtractionType',
    'ExtractionMethod',
    'ExtractionResult',
    'RouterConfig',
    'LLMRouter',
    'get_router',
    'extract',
]
