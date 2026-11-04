# ComfyUI workflows

Export each from ComfyUI with **Save (API Format)** and drop it here. Put
`{{TOKENS}}` in the text/seed/path fields; `comfy_client.fill()` substitutes them.

| file | purpose | tokens |
|---|---|---|
| `anchor_portrait.json` | design / refresh an anchor still (SDXL or Flux + FaceID/IPAdapter on `REF_IMAGE`) | `POSITIVE`, `NEGATIVE`, `SEED`, `REF_IMAGE`, `OUT_PREFIX` |
| `anchor_talking.json` | lip-synced talking head from the still + TTS audio (LatentSync / SadTalker / Wav2Lip nodes) | `REF_IMAGE`, `AUDIO_PATH`, `SEED`, `OUT_PREFIX` |
| `broll_still.json` | illustrative background still for a story (never a fake photo of a real event) | `POSITIVE`, `SEED`, `OUT_PREFIX` |

`AUDIO_PATH` / `REF_IMAGE` must be paths ComfyUI can read — put them in
ComfyUI's `input/` dir on kwon9000 (rsync over Tailscale) or use a
LoadImage-from-URL node.
