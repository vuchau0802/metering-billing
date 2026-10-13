from alembic.config import Config
from alembic.script import ScriptDirectory


def main() -> int:
    config = Config("alembic.ini")
    migrations = ScriptDirectory.from_config(config)
    heads = migrations.get_heads()

    if len(heads) != 1:
        print(
            "Expected exactly one Alembic head, "
            f"but found {len(heads)}: {heads}"
        )
        return 1

    print(f"Single Alembic head: {heads[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())