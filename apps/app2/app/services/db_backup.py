"""Backup e restauração do PostgreSQL (somente admin root)."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from sqlalchemy import create_engine, text

from app.config import settings

BACKUP_NAME_RE = re.compile(r"^assistfin_\d{8}_\d{6}\.dump$")
RESTORE_CONFIRM_WORD = "RESTAURAR"
DEFAULT_KEEP = 20

# Erros de SET gerados por cliente pg_dump mais novo que o servidor (ex.: 17 → 16).
_IGNORABLE_RESTORE_SNIPPETS = (
    'unrecognized configuration parameter "transaction_timeout"',
    'unrecognized configuration parameter "idle_session_timeout"',
)

_ESSENTIAL_TABLES = ("users", "accounts", "transactions", "alembic_version")


@dataclass(frozen=True)
class BackupInfo:
    filename: str
    size_bytes: int
    created_at: datetime

    @property
    def size_label(self) -> str:
        size = float(self.size_bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                if unit == "B":
                    return f"{int(size)} {unit}"
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{self.size_bytes} B"

    @property
    def created_label(self) -> str:
        return self.created_at.strftime("%d/%m/%Y %H:%M")


def backup_dir() -> Path:
    path = Path(getattr(settings, "backup_dir", None) or "/app/data/backups")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _db_conn() -> dict[str, str]:
    parsed = urlparse(settings.database_url)
    if parsed.scheme not in {"postgresql", "postgres", "postgresql+psycopg2"}:
        raise ValueError("DATABASE_URL inválida para backup.")
    if not parsed.hostname or not parsed.path or parsed.path == "/":
        raise ValueError("DATABASE_URL sem host ou nome do banco.")
    password = unquote(parsed.password or "")
    user = unquote(parsed.username or "")
    if not user:
        raise ValueError("DATABASE_URL sem usuário.")
    return {
        "host": parsed.hostname,
        "port": str(parsed.port or 5432),
        "user": user,
        "password": password,
        "dbname": parsed.path.lstrip("/"),
    }


def _env_with_password(password: str) -> dict[str, str]:
    env = os.environ.copy()
    env["PGPASSWORD"] = password
    env["PGOPTIONS"] = "-c client_min_messages=warning"
    return env


def safe_backup_filename(name: str) -> str:
    """Valida nome de arquivo (sem path traversal)."""
    filename = Path(name).name
    if filename != name or ".." in name or "/" in name or "\\" in name:
        raise ValueError("Nome de backup inválido.")
    if not BACKUP_NAME_RE.match(filename):
        raise ValueError("Nome de backup inválido.")
    return filename


def backup_path(filename: str) -> Path:
    safe = safe_backup_filename(filename)
    path = (backup_dir() / safe).resolve()
    if not str(path).startswith(str(backup_dir().resolve())):
        raise ValueError("Caminho de backup inválido.")
    return path


def list_backups() -> list[BackupInfo]:
    items: list[BackupInfo] = []
    for path in sorted(backup_dir().glob("assistfin_*.dump"), reverse=True):
        if not BACKUP_NAME_RE.match(path.name):
            continue
        stat = path.stat()
        items.append(
            BackupInfo(
                filename=path.name,
                size_bytes=stat.st_size,
                created_at=datetime.fromtimestamp(stat.st_mtime),
            )
        )
    return items


def _prune_old_backups(keep: int = DEFAULT_KEEP) -> None:
    backups = list_backups()
    for old in backups[keep:]:
        try:
            backup_path(old.filename).unlink(missing_ok=True)
        except OSError:
            pass


def create_backup() -> BackupInfo:
    """Gera dump custom (-Fc) com timestamp local."""
    conn = _db_conn()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"assistfin_{stamp}.dump"
    dest = backup_dir() / filename
    tmp = dest.with_suffix(".dump.partial")

    cmd = [
        "pg_dump",
        "-h",
        conn["host"],
        "-p",
        conn["port"],
        "-U",
        conn["user"],
        "-d",
        conn["dbname"],
        "-Fc",
        "--no-owner",
        "--no-acl",
        "-f",
        str(tmp),
    ]
    try:
        result = subprocess.run(
            cmd,
            env=_env_with_password(conn["password"]),
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        if result.returncode != 0:
            tmp.unlink(missing_ok=True)
            err = (result.stderr or result.stdout or "falha desconhecida").strip()
            raise ValueError(f"Falha ao criar backup: {err[:300]}")
        tmp.replace(dest)
    except FileNotFoundError as exc:
        tmp.unlink(missing_ok=True)
        raise ValueError(
            "Cliente PostgreSQL (pg_dump) não encontrado no container."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        tmp.unlink(missing_ok=True)
        raise ValueError("Tempo esgotado ao criar o backup.") from exc

    _prune_old_backups(keep=int(getattr(settings, "backup_keep", None) or DEFAULT_KEEP))
    stat = dest.stat()
    return BackupInfo(
        filename=filename,
        size_bytes=stat.st_size,
        created_at=datetime.fromtimestamp(stat.st_mtime),
    )


def _reset_public_schema() -> None:
    """Encerra sessões e recria o schema public (substitui --clean frágil)."""
    eng = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    try:
        with eng.connect() as conn:
            conn.execute(
                text(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                      AND pid <> pg_backend_pid()
                    """
                )
            )
            conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
            conn.execute(text("GRANT ALL ON SCHEMA public TO CURRENT_USER"))
    finally:
        eng.dispose()


def _assert_restore_complete() -> None:
    eng = create_engine(settings.database_url)
    try:
        with eng.connect() as conn:
            placeholders = ", ".join(f"'{t}'" for t in _ESSENTIAL_TABLES)
            found = conn.execute(
                text(
                    f"""
                    SELECT count(*) FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name IN ({placeholders})
                    """
                )
            ).scalar()
            if int(found or 0) < len(_ESSENTIAL_TABLES):
                raise ValueError(
                    "Restauração incompleta: tabelas essenciais ausentes após o restore."
                )
    finally:
        eng.dispose()


def _dispose_app_pool() -> None:
    """Descarta conexões do pool da app (schema/dados mudaram)."""
    try:
        from app.db import engine

        engine.dispose()
    except Exception:
        pass


def _restore_stderr_is_fatal(stderr: str) -> bool:
    """True se houver erro de pg_restore que não seja SET incompatível."""
    text_l = stderr.lower()
    if "authentication failed" in text_l or "could not connect" in text_l:
        return True
    for block in re.split(r"(?=pg_restore: error:)", stderr):
        block = block.strip()
        if not block.startswith("pg_restore: error:"):
            continue
        if any(snip in block.lower() for snip in _IGNORABLE_RESTORE_SNIPPETS):
            continue
        return True
    return False


def restore_backup(filename: str, *, confirm: str) -> str:
    """Restaura dump. Exige confirmação literal RESTAURAR."""
    if (confirm or "").strip() != RESTORE_CONFIRM_WORD:
        raise ValueError(
            f'Digite exatamente "{RESTORE_CONFIRM_WORD}" para confirmar a restauração.'
        )

    path = backup_path(filename)
    if not path.is_file():
        raise ValueError("Arquivo de backup não encontrado.")

    conn = _db_conn()
    # Libera conexões do pool da app antes de terminar backends / drop schema.
    _dispose_app_pool()
    try:
        _reset_public_schema()
    except Exception as exc:
        raise ValueError(f"Falha ao preparar o banco para restauração: {exc}") from exc

    cmd = [
        "pg_restore",
        "-h",
        conn["host"],
        "-p",
        conn["port"],
        "-U",
        conn["user"],
        "-d",
        conn["dbname"],
        "--no-owner",
        "--no-acl",
        str(path),
    ]
    try:
        result = subprocess.run(
            cmd,
            env=_env_with_password(conn["password"]),
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ValueError(
            "Cliente PostgreSQL (pg_restore) não encontrado no container."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Tempo esgotado ao restaurar o backup.") from exc

    stderr = result.stderr or ""
    if result.returncode not in {0, 1}:
        raise ValueError(
            f"Falha ao restaurar backup: {(stderr or result.stdout or 'falha desconhecida').strip()[:400]}"
        )
    if result.returncode == 1 and _restore_stderr_is_fatal(stderr):
        raise ValueError(f"Falha ao restaurar backup: {stderr.strip()[:400]}")

    try:
        _assert_restore_complete()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Falha ao validar restauração: {exc}") from exc
    finally:
        _dispose_app_pool()

    return filename


def delete_backup(filename: str) -> None:
    path = backup_path(filename)
    if not path.is_file():
        raise ValueError("Arquivo de backup não encontrado.")
    path.unlink()
