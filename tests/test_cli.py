import subprocess
import sys
from importlib.metadata import version

import pytest

import gminator
from gminator.cli import main


def test_package_version_matches_installed_metadata():
    assert gminator.__version__ == version("gminator")


def test_version_flag_prints_name_and_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"gminator {gminator.__version__}"


def test_module_is_runnable_with_python_m():
    result = subprocess.run(
        [sys.executable, "-m", "gminator", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == f"gminator {gminator.__version__}"
