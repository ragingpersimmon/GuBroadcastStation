# ComfyUI workflows (local anchor engine)

GBS doesn't ship node graphs, because node names and inputs change between custom-node versions. You build each workflow once in your own ComfyUI, check it works with the Run button, then convert it.

1. Build or load the workflow in ComfyUI and run it once by hand.
2. Export it with **Workflow → Export (API)** (older builds: Save (API Format)).
3. Convert it: `python -m gbs comfy-tokenize export.json --kind <kind>`
   This swaps the per-job inputs for `{{TOKENS}}`, writes `<kind>.json` here, and lists every swap. Fix anything it warns about by hand.

| kind | build it from | tokens |
|---|---|---|
| `anchor_talking` | **InfiniteTalk**: Kijai `ComfyUI-WanVideoWrapper` InfiniteTalk example (Wan2.1 I2V 480p + InfiniteTalk weights, **fp8 or GGUF**, from `Kijai/WanVideo_comfy`). Output via VHS_VideoCombine with audio at 25 fps. | `REF_IMAGE` `AUDIO_PATH` `NUM_FRAMES` `POSITIVE` `SEED` `OUT_PREFIX` |
| `tts` | **OmniVoice** (`Saganaki22/ComfyUI-OmniVoice-TTS`) or Chatterbox voice-clone node: LoadAudio reference → TTS → SaveAudio | `TEXT` `VOICE_REF` `SEED` `OUT_PREFIX` |
| `tts_design` | the same TTS pack, voice-design / instruct mode (no reference audio) | `TEXT` `VOICE_PROMPT` `SEED` `OUT_PREFIX` |
| `anchor_portrait` | any photoreal txt2img (Flux / SDXL) → SaveImage | `POSITIVE` `NEGATIVE` `SEED` `OUT_PREFIX` |

`NUM_FRAMES` is computed from the voice clip (25 fps, rounded to 4n+1 for Wan). If your InfiniteTalk graph sizes itself from the audio, delete that token. Portraits and audio are pushed to ComfyUI with its `/upload/image` endpoint, so nothing needs copying.

Use TTS models with commercial-use licences (OmniVoice is Apache-2.0; XTTS-v2 is non-commercial).
