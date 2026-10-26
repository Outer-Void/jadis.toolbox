import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from jadis.cli import main  # noqa: E402
from jadis.system import FakeSystem  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_system(name: str) -> FakeSystem:
    return FakeSystem.from_fixture(FIXTURES / f"{name}.json")


def run_cli(argv, system):
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(argv, system=system)
    text = out.getvalue()
    return code, (json.loads(text) if "--json" in argv or (argv and argv[0] == "blux-capability") else text)


@pytest.fixture
def fx():
    return fixture_system
