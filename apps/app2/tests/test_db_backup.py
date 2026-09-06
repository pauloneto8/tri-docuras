"""Testes do serviço de backup/restauração do banco."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services import db_backup


@pytest.fixture()
def backup_tmpdir(tmp_path, monkeypatch):
    monkeypatch.setattr(db_backup.settings, "backup_dir", str(tmp_path))
    monkeypatch.setattr(db_backup.settings, "backup_keep", 3)
    return tmp_path


def test_safe_backup_filename_rejects_traversal():
    with pytest.raises(ValueError):
        db_backup.safe_backup_filename("../etc/passwd")
    with pytest.raises(ValueError):
        db_backup.safe_backup_filename("assistfin_20260101_120000.dump/../x")
    with pytest.raises(ValueError):
        db_backup.safe_backup_filename("other.dump")
    assert (
        db_backup.safe_backup_filename("assistfin_20260101_120000.dump")
        == "assistfin_20260101_120000.dump"
    )


def test_list_and_prune_backups(backup_tmpdir):
    for i, stamp in enumerate(["20260101_010000", "20260101_020000", "20260101_030000", "20260101_040000"]):
        path = backup_tmpdir / f"assistfin_{stamp}.dump"
        path.write_bytes(b"x" * (10 + i))
        os.utime(path, (1_700_000_000 + i, 1_700_000_000 + i))

    listed = db_backup.list_backups()
    assert len(listed) == 4
    assert listed[0].filename.startswith("assistfin_")

    db_backup._prune_old_backups(keep=2)
    remaining = {p.name for p in backup_tmpdir.glob("*.dump")}
    assert len(remaining) == 2


def test_restore_requires_confirm_word(backup_tmpdir):
    name = "assistfin_20260101_120000.dump"
    (backup_tmpdir / name).write_bytes(b"dump")
    with pytest.raises(ValueError, match="RESTAURAR"):
        db_backup.restore_backup(name, confirm="restaurar")


def test_create_backup_calls_pg_dump(backup_tmpdir, monkeypatch):
    monkeypatch.setattr(
        db_backup.settings,
        "database_url",
        "postgresql://app2:secret@app2-db:5432/app2",
    )

    def fake_run(cmd, **kwargs):
        # último -f aponta para .partial
        out = Path(cmd[cmd.index("-f") + 1])
        out.write_bytes(b"FAKE_DUMP")
        return MagicMock(returncode=0, stderr="", stdout="")

    with patch("app.services.db_backup.subprocess.run", side_effect=fake_run) as mocked:
        info = db_backup.create_backup()

    assert info.filename.startswith("assistfin_")
    assert info.filename.endswith(".dump")
    assert (backup_tmpdir / info.filename).read_bytes() == b"FAKE_DUMP"
    mocked.assert_called_once()
    cmd = mocked.call_args[0][0]
    assert cmd[0] == "pg_dump"
    assert "-Fc" in cmd


def test_restore_backup_calls_pg_restore(backup_tmpdir, monkeypatch):
    monkeypatch.setattr(
        db_backup.settings,
        "database_url",
        "postgresql://app2:secret@app2-db:5432/app2",
    )
    name = "assistfin_20260101_120000.dump"
    (backup_tmpdir / name).write_bytes(b"dump")

    with (
        patch("app.services.db_backup._reset_public_schema") as reset,
        patch("app.services.db_backup._assert_restore_complete") as assert_ok,
        patch("app.services.db_backup._run_migrations_after_restore") as migrate,
        patch("app.services.db_backup._dispose_app_pool") as dispose,
        patch(
            "app.services.db_backup.subprocess.run",
            return_value=MagicMock(returncode=0, stderr="", stdout=""),
        ) as mocked,
    ):
        restored = db_backup.restore_backup(name, confirm="RESTAURAR")

    assert restored == name
    reset.assert_called_once()
    assert_ok.assert_called_once()
    migrate.assert_called_once()
    assert dispose.call_count == 2
    cmd = mocked.call_args[0][0]
    assert cmd[0] == "pg_restore"
    assert "--clean" not in cmd
    assert "--single-transaction" not in cmd
    assert "--no-owner" in cmd


def test_restore_ignores_transaction_timeout_error(backup_tmpdir, monkeypatch):
    monkeypatch.setattr(
        db_backup.settings,
        "database_url",
        "postgresql://app2:secret@app2-db:5432/app2",
    )
    name = "assistfin_20260101_120000.dump"
    (backup_tmpdir / name).write_bytes(b"dump")
    stderr = (
        'pg_restore: error: could not execute query: ERROR:  '
        'unrecognized configuration parameter "transaction_timeout"\n'
        "Command was: SET transaction_timeout = 0;\n"
        "pg_restore: warning: errors ignored on restore: 1\n"
    )

    with (
        patch("app.services.db_backup._reset_public_schema"),
        patch("app.services.db_backup._assert_restore_complete"),
        patch("app.services.db_backup._run_migrations_after_restore"),
        patch("app.services.db_backup._dispose_app_pool"),
        patch(
            "app.services.db_backup.subprocess.run",
            return_value=MagicMock(returncode=1, stderr=stderr, stdout=""),
        ),
    ):
        assert db_backup.restore_backup(name, confirm="RESTAURAR") == name


def test_restore_fails_on_real_pg_restore_error(backup_tmpdir, monkeypatch):
    monkeypatch.setattr(
        db_backup.settings,
        "database_url",
        "postgresql://app2:secret@app2-db:5432/app2",
    )
    name = "assistfin_20260101_120000.dump"
    (backup_tmpdir / name).write_bytes(b"dump")
    stderr = (
        "pg_restore: error: could not execute query: ERROR:  "
        "relation \"users\" already exists\n"
    )

    with (
        patch("app.services.db_backup._reset_public_schema"),
        patch("app.services.db_backup._assert_restore_complete"),
        patch("app.services.db_backup._run_migrations_after_restore"),
        patch("app.services.db_backup._dispose_app_pool"),
        patch(
            "app.services.db_backup.subprocess.run",
            return_value=MagicMock(returncode=1, stderr=stderr, stdout=""),
        ),
    ):
        with pytest.raises(ValueError, match="Falha ao restaurar"):
            db_backup.restore_backup(name, confirm="RESTAURAR")


def test_restore_stderr_is_fatal_helpers():
    assert not db_backup._restore_stderr_is_fatal(
        'unrecognized configuration parameter "transaction_timeout"'
    )
    assert db_backup._restore_stderr_is_fatal(
        "pg_restore: error: could not execute query: ERROR:  boom"
    )
    assert db_backup._restore_stderr_is_fatal("FATAL: password authentication failed")
