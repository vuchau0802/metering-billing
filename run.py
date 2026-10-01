from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config


ROOT = Path(__file__).resolve().parent


def apply_migrations() -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(ROOT / "alembic"),
    )
    command.upgrade(config, "head")


def main() -> None:
    apply_migrations()

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8004,
    )


if __name__ == "__main__":
    main()