from alembic.config import Config
from alembic.script import ScriptDirectory


def test_initial_migration_is_the_single_head():
    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert script.get_heads() == ["20261118_002"]
