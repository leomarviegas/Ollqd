"""Utility functions for data processing.

Known symbols: fibonacci, parse_csv, DataProcessor, validate_email
"""

import re
from dataclasses import dataclass
from typing import Iterator


def fibonacci(n: int) -> Iterator[int]:
    """Generate first n Fibonacci numbers."""
    a, b = 0, 1
    for _ in range(n):
        yield a
        a, b = b, a + b


def validate_email(email: str) -> bool:
    """Validate email format using regex."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def parse_csv(text: str, delimiter: str = ",") -> list[list[str]]:
    """Parse CSV text into rows."""
    rows = []
    for line in text.strip().splitlines():
        rows.append([cell.strip() for cell in line.split(delimiter)])
    return rows


@dataclass
class DataProcessor:
    """Processes data with configurable batch size."""

    batch_size: int = 32
    max_retries: int = 3

    def process_batch(self, items: list[str]) -> list[str]:
        """Process items in batches, returning transformed results."""
        results = []
        for i in range(0, len(items), self.batch_size):
            batch = items[i : i + self.batch_size]
            results.extend([item.upper() for item in batch])
        return results

    def validate_input(self, data: str) -> bool:
        """Check that input data is non-empty and under 10KB."""
        return bool(data) and len(data.encode()) < 10240
