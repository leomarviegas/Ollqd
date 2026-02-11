"""Shared fixtures for gRPC integration tests against the Python worker."""

import json
import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Add the generated proto stubs to sys.path so imports work:
#   from ollqd.v1 import processing_pb2, processing_pb2_grpc, types_pb2
# ---------------------------------------------------------------------------
_GEN_DIR = str(
    Path(__file__).resolve().parents[2] / "src" / "ollqd_worker" / "gen"
)
if _GEN_DIR not in sys.path:
    sys.path.insert(0, _GEN_DIR)

try:
    import grpc.aio  # noqa: E402 (must come after path setup)
    from ollqd.v1 import processing_pb2_grpc  # noqa: E402

    _GRPC_AVAILABLE = True
except ImportError:
    _GRPC_AVAILABLE = False

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
WORKER_ADDR = os.getenv("WORKER_ADDR", "localhost:50051")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"

# ---------------------------------------------------------------------------
# Custom pytest markers
# ---------------------------------------------------------------------------
requires_ollama = pytest.mark.skipif(
    os.getenv("SKIP_OLLAMA", "").lower() in ("1", "true", "yes"),
    reason="Ollama not available (SKIP_OLLAMA is set)",
)

requires_indexed = pytest.mark.skipif(
    os.getenv("HAS_INDEXED_DATA", "").lower() not in ("1", "true", "yes"),
    reason="No pre-indexed data available (set HAS_INDEXED_DATA=1 to enable)",
)

requires_smb = pytest.mark.skipif(
    not os.getenv("SMB_SERVER"),
    reason="SMB environment variables not configured (SMB_SERVER not set)",
)


# ---------------------------------------------------------------------------
# Async gRPC channel (session-scoped)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session")
async def grpc_channel():
    """Create an async gRPC channel to the Python worker and close on teardown."""
    if not _GRPC_AVAILABLE:
        pytest.skip("grpcio not installed; run: pip install grpcio grpcio-tools protobuf")
    channel = grpc.aio.insecure_channel(
        WORKER_ADDR,
        options=[
            ("grpc.max_receive_message_length", 64 * 1024 * 1024),
            ("grpc.max_send_message_length", 64 * 1024 * 1024),
        ],
    )
    # Verify the channel is connectable before returning it to tests.
    try:
        await channel.channel_ready()
    except Exception:
        pytest.skip(
            f"gRPC worker at {WORKER_ADDR} is not reachable; skipping gRPC tests"
        )
    yield channel
    await channel.close()


# ---------------------------------------------------------------------------
# Service stub fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session")
async def config_stub(grpc_channel):
    """ConfigService stub."""
    return processing_pb2_grpc.ConfigServiceStub(grpc_channel)


@pytest_asyncio.fixture(scope="session")
async def indexing_stub(grpc_channel):
    """IndexingService stub."""
    return processing_pb2_grpc.IndexingServiceStub(grpc_channel)


@pytest_asyncio.fixture(scope="session")
async def search_stub(grpc_channel):
    """SearchService stub."""
    return processing_pb2_grpc.SearchServiceStub(grpc_channel)


@pytest_asyncio.fixture(scope="session")
async def chat_stub(grpc_channel):
    """ChatService stub."""
    return processing_pb2_grpc.ChatServiceStub(grpc_channel)


@pytest_asyncio.fixture(scope="session")
async def embedding_stub(grpc_channel):
    """EmbeddingService stub."""
    return processing_pb2_grpc.EmbeddingServiceStub(grpc_channel)


@pytest_asyncio.fixture(scope="session")
async def pii_stub(grpc_channel):
    """PIIService stub."""
    return processing_pb2_grpc.PIIServiceStub(grpc_channel)


@pytest_asyncio.fixture(scope="session")
async def visualization_stub(grpc_channel):
    """VisualizationService stub."""
    return processing_pb2_grpc.VisualizationServiceStub(grpc_channel)


@pytest_asyncio.fixture(scope="session")
async def smb_stub(grpc_channel):
    """SMBService stub."""
    return processing_pb2_grpc.SMBServiceStub(grpc_channel)


# ---------------------------------------------------------------------------
# Fixture data helpers
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def fixtures_dir():
    """Absolute path to the tests/fixtures/ directory."""
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def pii_samples():
    """Load PII test samples from fixtures/pii/samples.json."""
    samples_path = FIXTURES_DIR / "pii" / "samples.json"
    with open(samples_path) as f:
        return json.load(f)["samples"]


@pytest.fixture(scope="session")
def codebase_fixtures_dir():
    """Absolute path to tests/fixtures/codebase/."""
    return FIXTURES_DIR / "codebase"


@pytest.fixture(scope="session")
def docs_fixtures_dir():
    """Absolute path to tests/fixtures/docs/."""
    return FIXTURES_DIR / "docs"


@pytest.fixture(scope="session")
def images_fixtures_dir():
    """Absolute path to tests/fixtures/images/."""
    return FIXTURES_DIR / "images"


# ---------------------------------------------------------------------------
# Ollama availability check
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session")
async def ollama_available():
    """Return True if Ollama is reachable, otherwise skip the test."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            if resp.status_code == 200:
                return True
    except Exception:
        pass
    pytest.skip(f"Ollama at {OLLAMA_URL} is not reachable")
