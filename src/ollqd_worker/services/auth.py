"""AuthService gRPC servicer — user authentication and management."""

import logging

import grpc

from .. import config_db

log = logging.getLogger("ollqd.worker.auth")

try:
    from ..gen.ollqd.v1 import processing_pb2 as pb2
    from ..gen.ollqd.v1 import types_pb2
    _STUBS_AVAILABLE = True
except ImportError:
    _STUBS_AVAILABLE = False


class AuthServiceServicer:
    """gRPC servicer for authentication and user management."""

    async def Login(self, request, context):
        username = request.username
        password = request.password
        if not username or not password:
            return pb2.LoginResponse(success=False, error="username and password required")

        user = config_db.verify_user(username, password)
        if user is None:
            log.warning("Failed login attempt for user: %s", username)
            return pb2.LoginResponse(success=False, error="invalid credentials")

        log.info("User logged in: %s", username)
        return pb2.LoginResponse(
            success=True,
            username=user["username"],
            role=user["role"],
        )

    async def ValidateToken(self, request, context):
        # Token validation is handled at the gateway level.
        # This RPC exists for future use if needed.
        await context.abort(
            grpc.StatusCode.UNIMPLEMENTED,
            "token validation is handled by the gateway",
        )

    async def ListUsers(self, request, context):
        users = config_db.list_users()
        user_msgs = [
            types_pb2.User(
                username=u["username"],
                role=u["role"],
                created_at=u["created_at"],
            )
            for u in users
        ]
        return pb2.ListUsersResponse(users=user_msgs)

    async def CreateUser(self, request, context):
        username = request.username
        password = request.password
        role = request.role or "user"

        if not username or not password:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "username and password are required",
            )

        if role not in ("admin", "user"):
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "role must be 'admin' or 'user'",
            )

        user = config_db.create_user(username, password, role)
        if user is None:
            await context.abort(
                grpc.StatusCode.ALREADY_EXISTS,
                f"user '{username}' already exists",
            )

        log.info("Created user: %s (role=%s)", username, role)
        return pb2.CreateUserResponse(
            user=types_pb2.User(
                username=user["username"],
                role=user["role"],
                created_at=user["created_at"],
            )
        )

    async def DeleteUser(self, request, context):
        username = request.username
        if not username:
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "username is required",
            )

        ok, err = config_db.delete_user(username)
        if not ok:
            return pb2.DeleteUserResponse(deleted=False, error=err)

        log.info("Deleted user: %s", username)
        return pb2.DeleteUserResponse(deleted=True)
