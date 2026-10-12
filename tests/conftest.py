from dataclasses import dataclass
from pathlib import Path

import pytest

from sql_obfuscator.tokens import Dialect

SCRIPTS_DIR = Path(__file__).parent / "scripts"


@dataclass(frozen=True)
class Script:
    path: Path
    dialect: Dialect

    @property
    def sql(self) -> str:
        """The script text without a byte order mark and with its line endings untouched."""
        return self.path.read_bytes().decode("utf-8-sig")


def all_scripts() -> list[Script]:
    return [
        Script(path, dialect)
        for dialect in Dialect
        for path in sorted((SCRIPTS_DIR / dialect.value).glob("*.sql"))
    ]


@pytest.fixture(params=all_scripts(), ids=lambda script: script.path.name)
def script(request: pytest.FixtureRequest) -> Script:
    return request.param
