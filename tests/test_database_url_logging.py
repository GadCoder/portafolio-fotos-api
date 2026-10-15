import os
import subprocess
import sys


def test_importing_db_session_does_not_log_database_url_credentials():
    secret_marker = "DO_NOT_LOG_THIS"
    database_url = f"postgresql://user:{secret_marker}@localhost/db"
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sqlalchemy; sqlalchemy.create_engine = lambda *args, **kwargs: None; import db.session",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )

    assert secret_marker not in result.stdout
    assert secret_marker not in result.stderr
