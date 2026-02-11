Ollqd Test Fixture Documents
============================

This directory contains deterministic test documents for validating
the document indexing and search pipeline.

Files:
  - sample.md      Markdown architecture guide with known sentences
  - report.txt     Plain text report with structured sections

Known searchable phrases:
  - "quick brown fox jumps over the lazy dog"
  - "three-tier system"
  - "semantic similarity search"
  - "PII masking uses regex patterns"

These phrases are used in search validation tests to verify
that indexed documents return expected results with proper scoring.
