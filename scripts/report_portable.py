from __future__ import annotations

import json
import importlib.util
import sys
from pathlib import Path


def main() -> None:
    root = Path(sys.argv[1]).resolve()
    files = [path for path in root.rglob("*") if path.is_file()]
    forbidden = ("torch", "torchvision", "sentence_transformers", "reranker")
    relative = [path.relative_to(root).as_posix() for path in files]
    llama_spec = importlib.util.find_spec("llama_index.core")
    llama_root = Path(llama_spec.origin).parent if llama_spec and llama_spec.origin else None
    llama_source_bytes = sum(path.stat().st_size for path in llama_root.rglob("*") if path.is_file()) if llama_root else 0
    payload = {
        "format": "pyinstaller-onedir",
        "file_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
        "total_megabytes": round(sum(path.stat().st_size for path in files) / 1024 / 1024, 2),
        "llama_index_core_source_bytes": llama_source_bytes,
        "forbidden_dependency_hits": [name for name in relative if any(term in name.casefold() for term in forbidden)],
    }
    destination = root.parent / "portable-size-report.json"
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    if payload["forbidden_dependency_hits"]:
        raise SystemExit("Forbidden heavyweight dependencies were bundled")


if __name__ == "__main__":
    main()
