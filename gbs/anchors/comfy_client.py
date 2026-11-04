"""Minimal ComfyUI HTTP client for the anchor studio on the 5090 (StarNet).

Workflows are exported from ComfyUI with "Save (API Format)" into
gbs/anchors/workflows/*.json. Any string value in the workflow may contain
{{PLACEHOLDER}} tokens which are filled per job, e.g. {{POSITIVE}},
{{NEGATIVE}}, {{SEED}}, {{AUDIO_PATH}}, {{REF_IMAGE}}, {{OUT_PREFIX}}.
A value that is *exactly* "{{SEED}}" is substituted as an int.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

WORKFLOW_DIR = Path(__file__).parent / "workflows"


def load_workflow(name: str) -> dict:
    p = WORKFLOW_DIR / f"{name}.json"
    if not p.exists():
        raise FileNotFoundError(
            f"{p} missing -- export it from ComfyUI (Save (API Format)) and run "
            f"`python -m gbs comfy-tokenize <export.json> --kind {name}`")
    return json.loads(p.read_text())


def fill(node: Any, values: dict) -> Any:
    if isinstance(node, dict):
        return {k: fill(v, values) for k, v in node.items()}
    if isinstance(node, list):
        return [fill(v, values) for v in node]
    if isinstance(node, str) and "{{" in node:
        for k, v in values.items():
            tok = "{{" + k + "}}"
            if node == tok:
                return v  # keep native type (int seeds, floats)
            node = node.replace(tok, str(v))
    return node


class ComfyClient:
    def __init__(self, base_url: str, timeout: int = 30):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.client_id = uuid.uuid4().hex

    def _get(self, path: str) -> bytes:
        with urllib.request.urlopen(self.base + path, timeout=self.timeout) as r:
            return r.read()

    def healthy(self) -> bool:
        try:
            json.loads(self._get("/system_stats"))
            return True
        except Exception:
            return False

    def queue(self, workflow: dict) -> str:
        body = json.dumps({"prompt": workflow, "client_id": self.client_id}).encode()
        req = urllib.request.Request(self.base + "/prompt", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read())["prompt_id"]

    def wait(self, prompt_id: str, max_wait: float = 1800, poll: float = 3) -> dict:
        deadline = time.time() + max_wait
        while time.time() < deadline:
            hist = json.loads(self._get(f"/history/{prompt_id}"))
            if prompt_id in hist:
                entry = hist[prompt_id]
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise RuntimeError(f"ComfyUI job {prompt_id} failed: {status.get('messages')}")
                return entry.get("outputs", {})
            time.sleep(poll)
        raise TimeoutError(f"ComfyUI job {prompt_id} exceeded {max_wait}s")

    def download_outputs(self, outputs: dict, dest: Path) -> list[Path]:
        dest.mkdir(parents=True, exist_ok=True)
        saved = []
        for node_out in outputs.values():
            for kind in ("images", "gifs", "videos", "audio"):
                for f in node_out.get(kind, []):
                    q = urllib.parse.urlencode({"filename": f["filename"],
                                                "subfolder": f.get("subfolder", ""),
                                                "type": f.get("type", "output")})
                    p = dest / f["filename"]
                    p.write_bytes(self._get(f"/view?{q}"))
                    saved.append(p)
        return saved

    def upload(self, path: Path, subfolder: str = "gbs") -> str:
        """Push a local file (portrait, reference voice, TTS wav) into ComfyUI's
        input/ dir via /upload/image (accepts any file type). Returns the
        name to put in LoadImage / LoadAudio inputs ("subfolder/file")."""
        boundary = uuid.uuid4().hex
        data = path.read_bytes()
        parts = []
        for k, v in (("overwrite", "true"), ("type", "input"), ("subfolder", subfolder)):
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{path.name}"\r\n'
                      "Content-Type: application/octet-stream\r\n\r\n").encode() + data + b"\r\n")
        body = b"".join(parts) + f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(self.base + "/upload/image", data=body,
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            out = json.loads(r.read())
        return f"{out['subfolder']}/{out['name']}" if out.get("subfolder") else out["name"]

    def free(self) -> None:
        """Unload models and release VRAM so the LLM can have the GPU back."""
        req = urllib.request.Request(self.base + "/free", method="POST",
                                     data=json.dumps({"unload_models": True, "free_memory": True}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout):
            pass

    def run(self, workflow_name: str, values: dict, dest: Path) -> list[Path]:
        wf = load_workflow(workflow_name)
        pid = self.queue(fill(wf, values))
        return self.download_outputs(self.wait(pid), dest)
