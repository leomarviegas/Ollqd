"""Reversible PII masking service — regex patterns + optional spaCy NER."""

import enum
import logging
import re
from typing import Optional

log = logging.getLogger("ollqd.web.pii")

# ── Regex patterns for structured PII ────────────────────

_PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    )),
    ("PHONE", re.compile(
        r"(?<!\d)(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}(?!\d)"
    )),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")),
    ("IP_ADDRESS", re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    )),
    ("IBAN", re.compile(
        r"\b[A-Z]{2}\d{2}[\s]?[\dA-Z]{4}[\s]?(?:[\dA-Z]{4}[\s]?){2,7}[\dA-Z]{1,4}\b"
    )),
    ("DATE_OF_BIRTH", re.compile(
        r"\b(?:0[1-9]|1[0-2])[/-](?:0[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b"
    )),
]

# spaCy entity label -> PII type
_SPACY_LABEL_MAP = {
    "PERSON": "PERSON",
    "ORG": "ORG",
    "GPE": "LOCATION",
}

# System instruction prepended when PII tokens are present
PII_SYSTEM_INSTRUCTION = (
    "IMPORTANT: The user query and context below contain placeholder tokens "
    "(e.g. <PERSON_1>, <EMAIL_1>, <ORG_1>) that replace sensitive information. "
    "You MUST preserve these tokens exactly as-is in your response. "
    "Do NOT attempt to guess, decode, or replace the original values. "
    "Refer to entities by their token (e.g. 'According to <PERSON_1>...')."
)


# ── Entity Registry ──────────────────────────────────────


class EntityRegistry:
    """Bidirectional PII value <-> token map for one chat turn.

    Deterministic: same value always returns the same token within this registry.
    """

    def __init__(self) -> None:
        self._value_to_token: dict[str, str] = {}
        self._token_to_value: dict[str, str] = {}
        self._type_counters: dict[str, int] = {}

    def get_or_create_token(self, pii_type: str, value: str) -> str:
        key = value.strip()
        if key in self._value_to_token:
            return self._value_to_token[key]
        counter = self._type_counters.get(pii_type, 0) + 1
        self._type_counters[pii_type] = counter
        token = f"<{pii_type}_{counter}>"
        self._value_to_token[key] = token
        self._token_to_value[token] = key
        return token

    def unmask(self, text: str) -> str:
        result = text
        for token, value in self._token_to_value.items():
            result = result.replace(token, value)
        return result

    @property
    def token_to_value(self) -> dict[str, str]:
        return dict(self._token_to_value)

    @property
    def has_entities(self) -> bool:
        return len(self._value_to_token) > 0


# ── Stream Unmask Buffer ─────────────────────────────────


class _BufferState(enum.Enum):
    NORMAL = "normal"
    BUFFERING = "buffering"


class StreamUnmaskBuffer:
    """State machine for unmasking PII tokens in streaming LLM output.

    Handles tokens split across chunks (e.g. ``<PER`` + ``SON_1>``).

    States:
      NORMAL    -- pass through; on '<' switch to BUFFERING
      BUFFERING -- accumulate; on '>' check token map, emit unmasked or as-is
                   if buffer > MAX_TOKEN_LEN, flush as-is
    """

    MAX_TOKEN_LEN = 30

    def __init__(self, registry: EntityRegistry) -> None:
        self._registry = registry
        self._state = _BufferState.NORMAL
        self._buffer = ""

    def feed(self, chunk: str) -> str:
        parts: list[str] = []
        for char in chunk:
            if self._state == _BufferState.NORMAL:
                if char == "<":
                    self._state = _BufferState.BUFFERING
                    self._buffer = "<"
                else:
                    parts.append(char)
            elif self._state == _BufferState.BUFFERING:
                self._buffer += char
                if char == ">":
                    value = self._registry.token_to_value.get(self._buffer)
                    parts.append(value if value is not None else self._buffer)
                    self._buffer = ""
                    self._state = _BufferState.NORMAL
                elif len(self._buffer) > self.MAX_TOKEN_LEN:
                    parts.append(self._buffer)
                    self._buffer = ""
                    self._state = _BufferState.NORMAL
        return "".join(parts)

    def flush(self) -> str:
        remaining = self._buffer
        self._buffer = ""
        self._state = _BufferState.NORMAL
        return remaining


# ── PII Masking Service ──────────────────────────────────


class PIIMaskingService:
    """Detects and masks PII using regex patterns + optional spaCy NER.

    Thread-safe for detection. EntityRegistry is per-turn, created by caller.
    """

    def __init__(self, use_spacy: bool = True) -> None:
        self._use_spacy = use_spacy
        self._nlp = None  # lazy-loaded

    def _get_nlp(self):
        if self._nlp is None and self._use_spacy:
            try:
                import spacy
                self._nlp = spacy.load(
                    "en_core_web_sm",
                    disable=["parser", "lemmatizer", "textcat"],
                )
                log.info("spaCy en_core_web_sm loaded successfully")
            except (ImportError, OSError) as e:
                log.warning("spaCy not available, falling back to regex-only: %s", e)
                self._use_spacy = False
                self._nlp = None
        return self._nlp

    def _detect_regex(self, text: str) -> list[tuple[str, str, int, int]]:
        findings: list[tuple[str, str, int, int]] = []
        for pii_type, pattern in _PII_PATTERNS:
            for m in pattern.finditer(text):
                findings.append((pii_type, m.group(), m.start(), m.end()))
        return findings

    def _detect_ner(self, text: str) -> list[tuple[str, str, int, int]]:
        nlp = self._get_nlp()
        if nlp is None:
            return []
        findings: list[tuple[str, str, int, int]] = []
        doc = nlp(text)
        for ent in doc.ents:
            pii_type = _SPACY_LABEL_MAP.get(ent.label_)
            if pii_type and len(ent.text.strip()) > 1:
                findings.append((pii_type, ent.text.strip(), ent.start_char, ent.end_char))
        return findings

    def mask_text(self, text: str, registry: EntityRegistry) -> str:
        """Replace detected PII in *text* with tokens from *registry*.

        Regex runs first (higher precision for structured PII), then NER.
        Overlapping spans are de-duplicated (first/longest wins).
        Replacements are applied end-to-start to preserve character offsets.
        """
        if not text or len(text) < 2:
            return text

        findings = self._detect_regex(text)
        if self._use_spacy:
            findings.extend(self._detect_ner(text))

        # Sort by start position, prefer longer matches for ties
        findings.sort(key=lambda f: (f[2], -(f[3] - f[2])))

        # De-duplicate overlapping spans
        filtered: list[tuple[str, str, int, int]] = []
        last_end = -1
        for pii_type, value, start, end in findings:
            if start >= last_end:
                filtered.append((pii_type, value, start, end))
                last_end = end

        # Replace end-to-start
        result = text
        for pii_type, value, start, end in reversed(filtered):
            token = registry.get_or_create_token(pii_type, value)
            result = result[:start] + token + result[end:]

        return result

    def create_registry(self) -> EntityRegistry:
        return EntityRegistry()

    def create_stream_buffer(self, registry: EntityRegistry) -> StreamUnmaskBuffer:
        return StreamUnmaskBuffer(registry)

    @property
    def is_spacy_available(self) -> bool:
        return self._get_nlp() is not None
