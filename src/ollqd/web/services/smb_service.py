"""SMB/CIFS client service using pysmb — list, download, and browse remote shares."""

import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger("ollqd.web.smb")


@dataclass
class SMBShareConfig:
    id: str
    server: str
    share: str
    username: str = ""
    password: str = ""
    domain: str = ""
    port: int = 445
    label: str = ""

    @property
    def display_name(self) -> str:
        return self.label or f"//{self.server}/{self.share}"


class SMBManager:
    """In-memory store for SMB share configurations + operations."""

    def __init__(self):
        self._shares: dict[str, SMBShareConfig] = {}

    def add_share(self, config: SMBShareConfig) -> SMBShareConfig:
        self._shares[config.id] = config
        return config

    def remove_share(self, share_id: str) -> bool:
        return self._shares.pop(share_id, None) is not None

    def get_share(self, share_id: str) -> Optional[SMBShareConfig]:
        return self._shares.get(share_id)

    def list_shares(self) -> list[SMBShareConfig]:
        return list(self._shares.values())

    def _connect(self, config: SMBShareConfig):
        from smb.SMBConnection import SMBConnection

        conn = SMBConnection(
            config.username or "guest",
            config.password or "",
            "ollqd-client",
            config.server,
            domain=config.domain,
            use_ntlm_v2=True,
            is_direct_tcp=True,
        )
        if not conn.connect(config.server, config.port, timeout=10):
            raise ConnectionError(f"Cannot connect to {config.server}:{config.port}")
        return conn

    def list_remote_files(self, share_id: str, remote_path: str = "/") -> list[dict]:
        config = self._shares.get(share_id)
        if not config:
            raise ValueError(f"Share {share_id} not found")

        conn = self._connect(config)
        try:
            entries = conn.listPath(config.share, remote_path)
            result = []
            for e in entries:
                if e.filename in (".", ".."):
                    continue
                result.append({
                    "name": e.filename,
                    "is_dir": e.isDirectory,
                    "size": e.file_size,
                    "path": f"{remote_path.rstrip('/')}/{e.filename}",
                })
            return sorted(result, key=lambda x: (not x["is_dir"], x["name"].lower()))
        finally:
            conn.close()

    def download_files(
        self, share_id: str, remote_paths: list[str], dest_dir: Path,
    ) -> list[str]:
        """Download remote files to local dest_dir. Returns list of local paths."""
        config = self._shares.get(share_id)
        if not config:
            raise ValueError(f"Share {share_id} not found")

        conn = self._connect(config)
        local_paths = []
        try:
            for rp in remote_paths:
                filename = Path(rp).name
                local_path = dest_dir / filename
                with open(local_path, "wb") as f:
                    conn.retrieveFile(config.share, rp, f)
                local_paths.append(str(local_path))
        finally:
            conn.close()
        return local_paths

    def test_connection(self, config: SMBShareConfig) -> dict:
        """Test if we can connect and list the share root."""
        try:
            conn = self._connect(config)
            entries = conn.listPath(config.share, "/")
            conn.close()
            return {"ok": True, "files": len([e for e in entries if e.filename not in (".", "..")])}
        except Exception as e:
            return {"ok": False, "error": str(e)}
