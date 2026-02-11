"""Tests for the PII masking endpoint.

Routes tested:
  POST /api/system/config/pii/test

The PII test endpoint sends text to the gRPC PIIService.TestMasking RPC
and returns the masked text along with detected entities.
"""

import pytest


class TestPIITestEndpoint:
    """POST /api/system/config/pii/test"""

    def test_pii_test_endpoint(self, api, worker_available):
        """POST with sample text returns 200 with masked_text and entities."""
        if not worker_available:
            pytest.skip("gRPC worker not available for PII")

        r = api.post(
            "/api/system/config/pii/test",
            json={"text": "Contact John Smith at john@example.com"},
            timeout=15,
        )
        assert r.status_code == 200, f"PII test failed: {r.status_code}: {r.text}"
        data = r.json()
        assert isinstance(data, dict)
        # Response should contain the masked output
        assert (
            "masked" in data
            or "masked_text" in data
            or "maskedText" in data
        ), f"No masked text field in response: {data.keys()}"

    def test_pii_masks_email(self, api, worker_available):
        """An email address in the input text should be masked in the output."""
        if not worker_available:
            pytest.skip("gRPC worker not available for PII")

        original_email = "john.smith@example.com"
        r = api.post(
            "/api/system/config/pii/test",
            json={"text": f"Please contact {original_email} for details."},
            timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        masked = data.get("masked", data.get("masked_text", data.get("maskedText", "")))
        assert original_email not in masked, (
            f"Email was not masked: {masked}"
        )

    def test_pii_masks_phone(self, api, worker_available):
        """A US phone number in the input text should be masked."""
        if not worker_available:
            pytest.skip("gRPC worker not available for PII")

        phone = "+1-555-867-5309"
        r = api.post(
            "/api/system/config/pii/test",
            json={"text": f"Call Sarah at {phone} for the meeting."},
            timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        masked = data.get("masked", data.get("masked_text", data.get("maskedText", "")))
        # The exact phone format may differ, so check the main digits
        assert "555-867-5309" not in masked, (
            f"Phone was not masked: {masked}"
        )

    def test_pii_no_entities_unchanged(self, api, worker_available):
        """Text without PII entities should be returned unchanged."""
        if not worker_available:
            pytest.skip("gRPC worker not available for PII")

        text = "The system processes data in batches of 32 using vector embeddings."
        r = api.post(
            "/api/system/config/pii/test",
            json={"text": text},
            timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        masked = data.get("masked", data.get("masked_text", data.get("maskedText", "")))
        assert masked == text, (
            f"Text without PII was modified: '{masked}' vs '{text}'"
        )

    def test_pii_multi_entity(self, api, worker_available):
        """Multiple entity types (PERSON, EMAIL, PHONE) should all be masked."""
        if not worker_available:
            pytest.skip("gRPC worker not available for PII")

        text = (
            "Employee Jane Doe (jane.doe@company.org, 202-555-0147) "
            "reported to Michael Brown at the New York office."
        )
        r = api.post(
            "/api/system/config/pii/test",
            json={"text": text},
            timeout=15,
        )
        assert r.status_code == 200
        data = r.json()
        masked = data.get("masked", data.get("masked_text", data.get("maskedText", "")))

        # All PII values should be absent from the masked text
        for pii_value in ["Jane Doe", "jane.doe@company.org", "202-555-0147", "Michael Brown"]:
            assert pii_value not in masked, (
                f"PII value '{pii_value}' was not masked in: {masked}"
            )


class TestPIIWithFixtures:
    """Use the shared pii_samples fixture for data-driven PII tests."""

    def test_pii_samples_masking(self, api, worker_available, pii_samples):
        """Run all PII fixture samples through the masking endpoint."""
        if not worker_available:
            pytest.skip("gRPC worker not available for PII")

        for sample in pii_samples:
            text = sample["text"]
            r = api.post(
                "/api/system/config/pii/test",
                json={"text": text},
                timeout=15,
            )
            assert r.status_code == 200, (
                f"PII test failed for sample '{sample['id']}': {r.text}"
            )
            data = r.json()
            masked = data.get("masked", data.get("masked_text", data.get("maskedText", "")))

            # If sample expects masked text to equal original, verify that
            if sample.get("expected_masked_equals_original"):
                assert masked == text, (
                    f"Sample '{sample['id']}': expected unchanged, got '{masked}'"
                )

            # If sample expects certain strings NOT in masked output
            for not_contains in sample.get("expected_masked_not_contains", []):
                assert not_contains not in masked, (
                    f"Sample '{sample['id']}': '{not_contains}' should be masked in '{masked}'"
                )
