from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from websockets.sync.client import connect


def _port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _request(socket, action: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    request_id = f"smoke-{time.time_ns()}"
    socket.send(json.dumps({"request_id": request_id, "action": action, "payload": payload or {}}))
    while True:
        response = json.loads(socket.recv())
        if response.get("request_id") != request_id or response.get("type") == "progress":
            continue
        if not response.get("ok"):
            raise AssertionError(f"Packaged action {action} failed: {response.get('error')}")
        return dict(response.get("payload") or {})


def _credentials(repo_root: Path) -> tuple[str, str, str, str]:
    path = Path(os.environ.get("SUBSTRATE_OPERATIONAL_KEY_FILE") or repo_root / "KEY.txt")
    lines = [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if len(lines) < 4:
        raise RuntimeError("Operational credential contract is unavailable")
    return lines[0], lines[1].rstrip("/"), lines[2].rstrip("/"), lines[3]


def _reset_runtime(portable: Path) -> None:
    for name in ("data",):
        target = (portable / name).resolve()
        if target.parent != portable.resolve():
            raise RuntimeError("Unsafe portable cleanup target")
        if target.exists():
            shutil.rmtree(target)
        target.mkdir()
    knowledge = portable / "workspace" / "knowledge"
    if knowledge.exists():
        for item in knowledge.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
    else:
        knowledge.mkdir(parents=True)
    (portable / "workspace" / "persona.md").write_text("# Persona\n\nConfigure this file before use.\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("portable", type=Path)
    parser.add_argument("--real-providers", action="store_true")
    args = parser.parse_args()
    portable = args.portable.resolve()
    executable = portable / "VirtualMate.exe"
    if not executable.is_file():
        raise SystemExit("Packaged executable is missing")
    repo_root = Path(__file__).resolve().parents[4]
    _reset_runtime(portable)
    port = _port()
    environment = {**os.environ, "VSA_PORT": str(port), "VSA_OPEN_BROWSER": "0"}
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen([str(executable)], cwd=portable, env=environment, creationflags=creation_flags)
    try:
        deadline = time.monotonic() + 45
        while True:
            try:
                response = httpx.get(f"http://127.0.0.1:{port}/api/bootstrap", timeout=1)
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if process.poll() is not None:
                raise AssertionError(f"Packaged executable exited with code {process.returncode}")
            if time.monotonic() > deadline:
                raise AssertionError("Packaged executable did not become ready")
            time.sleep(0.25)
        assert response.json()["paths"]["workspace"] == str(portable / "workspace")
        index = httpx.get(f"http://127.0.0.1:{port}/", timeout=5).text
        assert '<div id="root"></div>' in index
        assert httpx.get(f"http://127.0.0.1:{port}/assets/app.js", timeout=5).status_code == 200
        assert httpx.get(f"http://127.0.0.1:{port}/assets/app.css", timeout=5).status_code == 200
        if args.real_providers:
            openrouter_key, openrouter_url, embeddings_url, embeddings_key = _credentials(repo_root)
            workspace = portable / "workspace"
            (workspace / "persona.md").write_text("# Ada Vega\n\nYou are Ada Vega. Answer concisely and cite project evidence.\n", encoding="utf-8")
            (workspace / "knowledge" / "portable_smoke.md").write_text("# Portable fact\n\nThe packaged verification marker is PORTABLE-RAG-731.\n", encoding="utf-8")
            with connect(f"ws://127.0.0.1:{port}/ws", open_timeout=10) as socket:
                _request(socket, "reload_persona")
                _request(socket, "save_model_server", {"server": {"id": "or", "alias": "OpenRouter", "base_url": openrouter_url, "api_key": openrouter_key}})
                _request(socket, "save_model_server", {"server": {"id": "emb", "alias": "Embeddings", "base_url": embeddings_url, "api_key": embeddings_key}})
                _request(socket, "assign_roles", {"chat": {"server_id": "or", "model_id": "mistralai/ministral-14b-2512"}, "embeddings": {"server_id": "emb", "model_id": "Alibaba-NLP/gte-multilingual-base"}})
                processed = _request(socket, "process_knowledge")
                assert processed["documents_processed"] == 1 and processed["chunks_generated"] >= 1
                answer = _request(socket, "chat", {"message": "What is the packaged verification marker?"})
                assert "PORTABLE-RAG-731" in str(answer["answer"])
                assert answer["evidence"]
        print(json.dumps({"status": "passed", "portable": str(portable), "real_providers": args.real_providers}))
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        _reset_runtime(portable)


if __name__ == "__main__":
    main()

