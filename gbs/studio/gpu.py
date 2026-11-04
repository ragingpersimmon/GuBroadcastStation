"""GPU handoff on the 5090: the 27B LLM and InfiniteTalk can't share 32 GB,
so each render window goes   LLM out -> ComfyUI in -> ComfyUI /free -> LLM back.

GBS_GPU_HANDOFF = none | ollama | command
  ollama   POST {OLLAMA_URL}/api/generate {"model": LLM_MODEL, "keep_alive": 0}
           unloads; the next request reloads it automatically.
  command  run GBS_LLM_UNLOAD_CMD before and GBS_LLM_RELOAD_CMD after
           (e.g. `ssh kwon9000 systemctl stop llama-server`, or a PowerShell
           Stop-Process / Start-Process line when running on the PC itself).
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import urllib.request
from contextlib import contextmanager

log = logging.getLogger("gbs.gpu")


def _run(cmd: str) -> None:
    if cmd:
        log.info("gpu handoff: %s", cmd)
        subprocess.run(cmd, shell=True, check=False, timeout=300)


def _ollama_unload() -> None:
    url = os.getenv("OLLAMA_URL", "http://kwon9000:11434").rstrip("/")
    body = json.dumps({"model": os.getenv("LLM_MODEL", ""), "keep_alive": 0}).encode()
    try:
        req = urllib.request.Request(url + "/api/generate", data=body,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=60).read()
    except Exception as exc:
        log.warning("ollama unload failed: %s", exc)


@contextmanager
def gpu_for_render(comfy=None):
    mode = os.getenv("GBS_GPU_HANDOFF", "none").strip().lower()
    if mode == "ollama":
        _ollama_unload()
    elif mode == "command":
        _run(os.getenv("GBS_LLM_UNLOAD_CMD", ""))
    try:
        yield
    finally:
        if comfy is not None and mode != "none":
            try:
                comfy.free()
            except Exception as exc:
                log.warning("ComfyUI /free failed: %s", exc)
        if mode == "command":
            _run(os.getenv("GBS_LLM_RELOAD_CMD", ""))
