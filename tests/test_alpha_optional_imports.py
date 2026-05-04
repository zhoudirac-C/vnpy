import importlib.util
import subprocess
import sys

import pytest


def test_alpha_package_import_is_lightweight_without_alpha_extra():
    """Importing vnpy.alpha should not require optional alpha research dependencies."""
    result = subprocess.run(
        [sys.executable, "-c", "import vnpy.alpha; print('ok')"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_alpha_utility_import_with_polars_does_not_require_alphalens():
    """Expression utilities need polars, but should not eagerly require alphalens."""
    pytest.importorskip("polars")

    from vnpy.alpha.dataset.utility import calculate_by_expression

    assert calculate_by_expression.__name__ == "calculate_by_expression"


def test_alpha_dataset_import_with_polars_does_not_require_alphalens():
    """AlphaDataset construction API should import without alphalens tear-sheet deps."""
    pytest.importorskip("polars")

    from vnpy.alpha import AlphaDataset

    assert AlphaDataset.__name__ == "AlphaDataset"


def test_alphalens_methods_report_install_hint_when_dependency_missing():
    """Tear-sheet helpers should fail with a direct optional-extra install hint."""
    pytest.importorskip("polars")
    if importlib.util.find_spec("alphalens") is not None:
        pytest.skip("alphalens is installed in this environment")

    from vnpy.alpha.dataset.template import _load_alphalens

    with pytest.raises(RuntimeError, match="uv sync --extra alpha"):
        _load_alphalens()
