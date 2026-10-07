import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.integration
def test_alembic_migration_works_on_live_postgresql():
    database_url = os.environ.get("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("Set TEST_POSTGRES_URL to run the live PostgreSQL migration test.")

    root = Path(__file__).resolve().parents[1]
    alembic_executable = shutil.which("alembic") or "alembic"
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["PROCESSING_MODE"] = "sync"

    upgrade = subprocess.run(
        [alembic_executable, "upgrade", "head"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert upgrade.returncode == 0, upgrade.stderr or upgrade.stdout
