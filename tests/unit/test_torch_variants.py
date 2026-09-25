"""Guard the CPU / CUDA torch split in pyproject.toml.

PyPI's Windows torch is CPU-only, so an NVIDIA GPU sat idle. The `cuda` extra
pulls torch from PyTorch's CUDA index on Windows; the `cpu` extra keeps PyPI
torch everywhere else (on macOS that is the MPS-capable build). The two must
never mix, and neither may leak into the base dependencies — otherwise one
variant silently gets the other's torch.
"""

import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
PYPROJECT = tomllib.loads((REPO / "pyproject.toml").read_text())
EXTRAS = PYPROJECT["project"]["optional-dependencies"]


def _names(reqs):
    return {r.split(">")[0].split("=")[0].split("<")[0].split(";")[0].strip() for r in reqs}


def test_torch_is_not_a_base_dependency():
    assert "torch" not in _names(PYPROJECT["project"]["dependencies"])


def test_both_variants_bring_torch():
    assert "torch" in _names(EXTRAS["cpu"])
    assert "torch" in _names(EXTRAS["cuda"])


def test_variants_conflict():
    assert [{"extra": "cpu"}, {"extra": "cuda"}] in PYPROJECT["tool"]["uv"]["conflicts"]


def test_cuda_torch_comes_from_pytorch_index_on_windows_only():
    sources = PYPROJECT["tool"]["uv"]["sources"]["torch"]
    sources = sources if isinstance(sources, list) else [sources]
    cuda = [s for s in sources if s.get("extra") == "cuda"]
    assert len(cuda) == 1
    assert cuda[0]["marker"] == "sys_platform == 'win32'"
    index = {i["name"]: i for i in PYPROJECT["tool"]["uv"]["index"]}[cuda[0]["index"]]
    assert index["url"].startswith("https://download.pytorch.org/whl/cu")
    assert index["explicit"] is True
    # The cpu extra has no source override: plain PyPI torch.
    assert not [s for s in sources if s.get("extra") == "cpu"]
