import os
import shutil
import subprocess
from pathlib import Path


def test_alembic_migration_upgrade_and_downgrade_on_sqlite(tmp_path):
    database = tmp_path / "migration.sqlite3"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+pysqlite:///{database}"
    env["PROCESSING_MODE"] = "sync"

    root = Path(__file__).resolve().parents[1]
    alembic_executable = shutil.which("alembic") or "alembic"
    upgrade = subprocess.run(
        [alembic_executable, "upgrade", "head"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert upgrade.returncode == 0, upgrade.stderr or upgrade.stdout

    downgrade = subprocess.run(
        [alembic_executable, "downgrade", "base"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert downgrade.returncode == 0, downgrade.stderr or downgrade.stdout
