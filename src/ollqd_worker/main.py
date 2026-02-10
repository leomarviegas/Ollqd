"""gRPC server entry point for the Ollqd worker.

Registers all servicers and starts the async gRPC server.
Listens on [::]:50051 by default (configurable via GRPC_PORT env var).
"""

import asyncio
import logging
import os
import signal
import sys

import grpc
from grpc import aio as grpc_aio

from . import config_db
from .services.chat import ChatServiceServicer
from .services.config_svc import ConfigServiceServicer
from .services.embedding import EmbeddingServiceServicer
from .services.indexing import IndexingServiceServicer
from .services.pii import PIIServiceServicer
from .services.search import SearchServiceServicer
from .services.visualization import VisualizationServiceServicer

log = logging.getLogger("ollqd.worker")

# Try importing generated stubs for service registration.
# All services are in processing_pb2_grpc (generated from processing.proto).
_pb2_grpc = None
try:
    from .gen.ollqd.v1 import processing_pb2_grpc as _pb2_grpc
except ImportError:
    pass


def _register_servicers(server: grpc_aio.Server) -> list[str]:
    """Register all available servicers on the gRPC server.

    Returns list of registered service names for logging.
    """
    if _pb2_grpc is None:
        log.warning("Proto stubs not found (processing_pb2_grpc). No services registered.")
        return []

    registered = []
    svc_map = [
        ("ConfigService", ConfigServiceServicer(), _pb2_grpc.add_ConfigServiceServicer_to_server),
        ("EmbeddingService", EmbeddingServiceServicer(), _pb2_grpc.add_EmbeddingServiceServicer_to_server),
        ("PIIService", PIIServiceServicer(), _pb2_grpc.add_PIIServiceServicer_to_server),
        ("SearchService", SearchServiceServicer(), _pb2_grpc.add_SearchServiceServicer_to_server),
        ("ChatService", ChatServiceServicer(), _pb2_grpc.add_ChatServiceServicer_to_server),
        ("IndexingService", IndexingServiceServicer(), _pb2_grpc.add_IndexingServiceServicer_to_server),
        ("VisualizationService", VisualizationServiceServicer(), _pb2_grpc.add_VisualizationServiceServicer_to_server),
    ]

    for name, servicer, register_fn in svc_map:
        register_fn(servicer, server)
        registered.append(name)

    return registered


async def serve():
    """Start the gRPC server and block until shutdown."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
    )

    # Initialise config persistence DB before any gRPC calls arrive
    config_db.init_db(os.getenv("CONFIG_DB_PATH", "/data/config.sqlite"))

    port = os.getenv("GRPC_PORT", "50051")
    listen_addr = f"[::]:{port}"

    # Initialize the async gRPC server
    server = grpc_aio.server(
        options=[
            ("grpc.max_send_message_length", 50 * 1024 * 1024),     # 50 MB
            ("grpc.max_receive_message_length", 50 * 1024 * 1024),  # 50 MB
        ]
    )

    # Register all servicers
    registered = _register_servicers(server)

    # Add the listening port
    server.add_insecure_port(listen_addr)

    # Start
    await server.start()

    if registered:
        log.info(
            "Ollqd gRPC worker started on %s with services: %s",
            listen_addr, ", ".join(registered),
        )
    else:
        log.warning(
            "Ollqd gRPC worker started on %s but NO services registered "
            "(proto stubs not yet generated). Run protoc first.",
            listen_addr,
        )

    # Graceful shutdown on SIGTERM/SIGINT
    shutdown_event = asyncio.Event()

    def _signal_handler():
        log.info("Shutdown signal received")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    await shutdown_event.wait()
    log.info("Shutting down gRPC server (5s grace period)...")
    await server.stop(grace=5)
    log.info("gRPC server stopped")


def main():
    """Entry point for `python -m ollqd_worker`."""
    asyncio.run(serve())


if __name__ == "__main__":
    main()
