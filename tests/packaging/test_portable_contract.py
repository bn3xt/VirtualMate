from __future__ import annotations

import ast
from pathlib import Path


PRODUCT_ROOT = Path(__file__).resolve().parents[2]


def test_pyinstaller_contract_is_onedir_and_excludes_heavy_model_stacks() -> None:
    spec = (PRODUCT_ROOT / "VirtualMate.spec").read_text(encoding="utf-8")
    assert "COLLECT(" in spec
    assert 'name="VirtualMate"' in spec
    for forbidden in ("torch", "torchvision", "sentence_transformers", "rerankers"):
        assert f'"{forbidden}"' in spec


def test_launcher_binds_only_loopback_and_uses_portable_app() -> None:
    source = (PRODUCT_ROOT / "backend" / "virtual_mate" / "launcher.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert 'host="127.0.0.1"' in source
    assert "from virtual_mate.app import app" in source


def test_runtime_manifest_has_no_local_models_or_reranker_stack() -> None:
    requirements = (PRODUCT_ROOT / "requirements.txt").read_text(encoding="utf-8").casefold()
    assert "llama-index-core" in requirements
    for forbidden in ("torch", "transformers", "sentence-transformers", "rerank"):
        assert forbidden not in requirements


def test_packaged_smoke_runner_resets_credentials_after_execution() -> None:
    source = (PRODUCT_ROOT / "tests" / "packaging" / "run_packaged_smoke.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert "_reset_runtime(portable)" in source
    assert "VSA_OPEN_BROWSER" in source

