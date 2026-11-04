"""Turn a ComfyUI "Save (API Format)" export into a GBS workflow template.

Node class names and input names differ between custom-node versions, so
instead of shipping hand-written graphs we take the workflow that already
works in your ComfyUI (e.g. Kijai's InfiniteTalk example, the OmniVoice
example) and swap the per-job inputs for {{TOKENS}}:

  anchor_talking  REF_IMAGE (LoadImage), AUDIO_PATH (LoadAudio*), NUM_FRAMES,
                  POSITIVE, SEED, OUT_PREFIX (VHS_VideoCombine / Save*)
  tts             TEXT, VOICE_REF (LoadAudio), SEED, OUT_PREFIX (SaveAudio*)
  tts_design      TEXT, VOICE_PROMPT (voice design / instruct), SEED, OUT_PREFIX
  anchor_portrait POSITIVE, NEGATIVE, SEED, REF_IMAGE (optional), OUT_PREFIX
"""
from __future__ import annotations

import json
from pathlib import Path

REQUIRED = {
    "anchor_talking": {"REF_IMAGE", "AUDIO_PATH", "OUT_PREFIX"},
    "tts": {"TEXT", "VOICE_REF", "OUT_PREFIX"},          # clone from a reference wav
    "tts_design": {"TEXT", "OUT_PREFIX"},                # design a voice from VOICE_PROMPT
    "anchor_portrait": {"POSITIVE", "OUT_PREFIX"},
}
SEED_KEYS = {"seed", "noise_seed"}
TTS_TEXT_KEYS = {"text", "tts_text", "input_text", "target_text", "gen_text"}
VOICE_PROMPT_KEYS = {"instruct", "instruction", "voice_description", "voice_prompt", "voice_design", "style_prompt"}
POS_KEYS, NEG_KEYS = {"positive_prompt", "positive"}, {"negative_prompt", "negative"}


def _is_link(v) -> bool:
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], str)


def tokenize(wf: dict, kind: str) -> tuple[dict, dict]:
    """Returns (templated workflow, {token: [node_id.input, ...]})."""
    if kind not in REQUIRED:
        raise ValueError(f"kind must be one of {sorted(REQUIRED)}")
    wf = json.loads(json.dumps(wf))
    hits: dict[str, list[str]] = {}

    def put(nid: str, key: str, token: str):
        wf[nid]["inputs"][key] = "{{" + token + "}}"
        hits.setdefault(token, []).append(f"{nid}.{key}")

    # pass 1: text prompts reached through sampler positive/negative links
    for nid, node in wf.items():
        ins = node.get("inputs", {})
        for key, token in (("positive", "POSITIVE"), ("negative", "NEGATIVE")):
            v = ins.get(key)
            if _is_link(v) and v[0] in wf:
                tgt = wf[v[0]]["inputs"]
                for tk in ("text", "prompt", "clip_l", "t5xxl"):
                    if isinstance(tgt.get(tk), str) and kind not in ("tts", "tts_design"):
                        put(v[0], tk, token)

    for nid, node in wf.items():
        ct = node.get("class_type", "")
        ins = node.get("inputs", {})
        low = ct.lower()
        for key, val in list(ins.items()):
            if _is_link(val):
                continue
            k = key.lower()
            if k in SEED_KEYS and isinstance(val, (int, float)):
                put(nid, key, "SEED")
            elif k == "filename_prefix":
                put(nid, key, "OUT_PREFIX")
            elif ct == "LoadImage" and k == "image" and kind not in ("tts", "tts_design"):
                put(nid, key, "REF_IMAGE")
            elif "loadaudio" in low and k in ("audio", "audio_file", "file"):
                put(nid, key, "VOICE_REF" if kind in ("tts", "tts_design") else "AUDIO_PATH")
            elif kind == "anchor_talking" and k in ("num_frames", "length", "frame_count") and isinstance(val, int):
                put(nid, key, "NUM_FRAMES")
            elif kind in ("tts", "tts_design") and k in TTS_TEXT_KEYS and isinstance(val, str):
                put(nid, key, "TEXT")
            elif kind in ("tts", "tts_design") and k in VOICE_PROMPT_KEYS and isinstance(val, str):
                put(nid, key, "VOICE_PROMPT")
            elif kind not in ("tts", "tts_design") and k in POS_KEYS and isinstance(val, str):
                put(nid, key, "POSITIVE")
            elif kind not in ("tts", "tts_design") and k in NEG_KEYS and isinstance(val, str):
                put(nid, key, "NEGATIVE")
    return wf, hits


def tokenize_file(src: Path, kind: str, dest_dir: Path) -> tuple[Path, dict, set]:
    wf = json.loads(src.read_text())
    if "nodes" in wf and "links" in wf:
        raise ValueError("this is a UI-format workflow; in ComfyUI use Workflow > Export (API) / Save (API Format)")
    out, hits = tokenize(wf, kind)
    missing = REQUIRED[kind] - set(hits)
    dest = dest_dir / f"{kind}.json"
    dest.write_text(json.dumps(out, indent=1))
    return dest, hits, missing
