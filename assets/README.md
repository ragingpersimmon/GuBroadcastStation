# Anchor assets

- `anchors/<id>.png` — the locked portrait for each character. Generate with `python -m gbs comfy-portraits`, pick the one you like, and commit it. InfiniteTalk animates this exact image every time, so the face stays consistent.
- `voices/<id>.wav` — optional 10–30 s clean reference for voice cloning. Without one, the TTS workflow designs a voice from the character's `voice_prompt` (OmniVoice voice design). Clone only voices you have rights to: invented voices, or your own.
