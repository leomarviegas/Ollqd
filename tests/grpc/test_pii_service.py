"""Integration tests for PIIService gRPC endpoints.

Tests cover the TestMasking RPC with various PII entity types.
Test data is loaded from tests/fixtures/pii/samples.json.
"""

import json

import pytest

from ollqd.v1 import processing_pb2


# ---------------------------------------------------------------------------
# Parametrize helper: build test cases from the samples.json fixture.
# ---------------------------------------------------------------------------
def _load_pii_samples():
    """Load samples at module level for parametrize (before fixtures are available)."""
    import pathlib

    samples_path = (
        pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "pii" / "samples.json"
    )
    with open(samples_path) as f:
        return json.load(f)["samples"]


_PII_SAMPLES = _load_pii_samples()


def _get_sample(sample_id: str) -> dict:
    """Retrieve a single sample by its id."""
    for s in _PII_SAMPLES:
        if s["id"] == sample_id:
            return s
    raise ValueError(f"Unknown sample id: {sample_id}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestMaskEmail:
    """Masking of email addresses."""

    @pytest.mark.asyncio
    async def test_mask_email(self, pii_stub):
        """Text containing an email should have it replaced with <EMAIL_1> (or similar)."""
        sample = _get_sample("email_simple")
        resp = await pii_stub.TestMasking(
            processing_pb2.TestMaskingRequest(text=sample["text"])
        )

        assert resp.original == sample["text"], "original field should echo input"
        assert resp.masked != resp.original, "Masked text should differ from original"
        assert resp.entity_count > 0, "Should detect at least one entity"

        # The email must be removed from the masked output
        for forbidden in sample["expected_masked_not_contains"]:
            assert forbidden not in resp.masked, (
                f"Masked output should not contain '{forbidden}'"
            )


class TestMaskPhone:
    """Masking of phone numbers."""

    @pytest.mark.asyncio
    async def test_mask_phone(self, pii_stub):
        """Text containing a phone number should have it masked."""
        sample = _get_sample("phone_us")
        resp = await pii_stub.TestMasking(
            processing_pb2.TestMaskingRequest(text=sample["text"])
        )

        assert resp.entity_count > 0
        for forbidden in sample["expected_masked_not_contains"]:
            assert forbidden not in resp.masked, (
                f"Masked output should not contain '{forbidden}'"
            )


class TestMaskMultipleEntities:
    """Masking of multiple PII entity types in a single text."""

    @pytest.mark.asyncio
    async def test_mask_multiple_entities(self, pii_stub):
        """Text with multiple PII types should have all of them masked."""
        sample = _get_sample("multi_entity")
        resp = await pii_stub.TestMasking(
            processing_pb2.TestMaskingRequest(text=sample["text"])
        )

        # Multiple entities should be detected
        assert resp.entity_count >= 2, (
            f"Expected at least 2 entities, got {resp.entity_count}"
        )

        for forbidden in sample["expected_masked_not_contains"]:
            assert forbidden not in resp.masked, (
                f"Masked output should not contain '{forbidden}'"
            )


class TestNoPII:
    """Text without PII should pass through unchanged."""

    @pytest.mark.asyncio
    async def test_no_pii_unchanged(self, pii_stub):
        """Clean text with no PII should be returned unchanged."""
        sample = _get_sample("no_pii")
        resp = await pii_stub.TestMasking(
            processing_pb2.TestMaskingRequest(text=sample["text"])
        )

        assert resp.masked == resp.original, (
            "Text without PII should have masked == original"
        )
        assert resp.entity_count == 0, "No entities should be detected"


class TestMaskSSN:
    """Masking of Social Security Numbers."""

    @pytest.mark.asyncio
    async def test_mask_ssn(self, pii_stub):
        """Text containing an SSN should have it masked."""
        sample = _get_sample("ssn")
        resp = await pii_stub.TestMasking(
            processing_pb2.TestMaskingRequest(text=sample["text"])
        )

        assert resp.entity_count > 0
        for forbidden in sample["expected_masked_not_contains"]:
            assert forbidden not in resp.masked, (
                f"Masked output should not contain '{forbidden}'"
            )


class TestMaskIBAN:
    """Masking of IBAN bank account numbers."""

    @pytest.mark.asyncio
    async def test_mask_iban(self, pii_stub):
        """Text containing an IBAN should have it masked."""
        sample = _get_sample("iban")
        resp = await pii_stub.TestMasking(
            processing_pb2.TestMaskingRequest(text=sample["text"])
        )

        assert resp.entity_count > 0
        for forbidden in sample["expected_masked_not_contains"]:
            assert forbidden not in resp.masked, (
                f"Masked output should not contain '{forbidden}'"
            )


class TestMaskCreditCard:
    """Masking of credit card numbers."""

    @pytest.mark.asyncio
    async def test_mask_credit_card(self, pii_stub):
        """Text containing a credit card number should have it masked."""
        sample = _get_sample("credit_card")
        resp = await pii_stub.TestMasking(
            processing_pb2.TestMaskingRequest(text=sample["text"])
        )

        assert resp.entity_count > 0
        for forbidden in sample["expected_masked_not_contains"]:
            assert forbidden not in resp.masked, (
                f"Masked output should not contain '{forbidden}'"
            )


class TestMaskIPAddress:
    """Masking of IP addresses."""

    @pytest.mark.asyncio
    async def test_mask_ip_address(self, pii_stub):
        """Text containing an IP address should have it masked."""
        sample = _get_sample("ip_address")
        resp = await pii_stub.TestMasking(
            processing_pb2.TestMaskingRequest(text=sample["text"])
        )

        assert resp.entity_count > 0
        for forbidden in sample["expected_masked_not_contains"]:
            assert forbidden not in resp.masked, (
                f"Masked output should not contain '{forbidden}'"
            )


# ---------------------------------------------------------------------------
# Parametrized test across ALL samples
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "sample",
    _PII_SAMPLES,
    ids=[s["id"] for s in _PII_SAMPLES],
)
class TestPIIMaskingParametrized:
    """Parametrized tests driven by fixtures/pii/samples.json."""

    @pytest.mark.asyncio
    async def test_masking_removes_pii(self, pii_stub, sample):
        """For each sample, verify that expected PII tokens are not in the masked output."""
        resp = await pii_stub.TestMasking(
            processing_pb2.TestMaskingRequest(text=sample["text"])
        )

        assert resp.original == sample["text"]

        # If the sample expects no PII, verify equality
        if sample.get("expected_masked_equals_original"):
            assert resp.masked == resp.original, (
                f"Sample '{sample['id']}': no-PII text should be returned unchanged"
            )
            assert resp.entity_count == 0
            return

        # Otherwise, all forbidden strings must be absent from masked output
        not_contains = sample.get("expected_masked_not_contains", [])
        for forbidden in not_contains:
            assert forbidden not in resp.masked, (
                f"Sample '{sample['id']}': masked output should not contain '{forbidden}'"
            )

    @pytest.mark.asyncio
    async def test_entity_list_populated(self, pii_stub, sample):
        """For samples with expected entities, verify the entities list is populated."""
        resp = await pii_stub.TestMasking(
            processing_pb2.TestMaskingRequest(text=sample["text"])
        )

        expected = sample.get("expected_entities", [])
        if expected:
            assert resp.entity_count > 0, (
                f"Sample '{sample['id']}': expected entities {expected} but got 0"
            )
            assert len(resp.entities) > 0, (
                f"Sample '{sample['id']}': entities list should be non-empty"
            )
        else:
            assert resp.entity_count == 0, (
                f"Sample '{sample['id']}': expected no entities but got {resp.entity_count}"
            )
