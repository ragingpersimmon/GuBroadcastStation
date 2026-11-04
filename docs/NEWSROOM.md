# Gu Broadcasting Station: newsroom → code

Everything lives in `config/newsroom.json`. Every on-air character is a fictional, AI-generated presenter (rendered locally with InfiniteTalk; each has a `look_prompt` and `voice_prompt` in its `comfy` block), and `/about.html` says so. Check with `python -m gbs newsroom`.

## Shows (show clock, `GBS_TZ`)

| Show | Anchor | When | Video |
|---|---|---|---|
| Gu Morning | Benji Powers | Mon–Fri 05:00–10:00 | top 4 entries at :00 and :30 |
| Gu Evening News | Tessa Vale | Mon–Fri 16:00–20:00 | top 4 entries at :00 and :30 |
| Gu Weekend | Nick Laba | Sat–Sun 07:00–20:00 | top 3 entries at :00 |
| Gu-cast | NOVA | all other times, every 15 min | 1 entry at :00 |
| Breaking bumper | ECHO | any story with urgency ≥ 0.7, or 5protocol regime = crisis | rides the next render |

An edition is ordered: breaking (if any) → open (show anchor, ≤25 words) → stories → close.

## On air → desks (assignment desk, Dex Okafor)

| Reporter | Desks | Source |
|---|---|---|
| Marcus Bell | politics | NPR, Guardian, CBC politics feeds |
| Lena Moravec | world + all regional desks | BBC, Al Jazeera, Guardian, DW, France 24, UN, NHK, Korea Herald, CBC |
| Rafael Tertelbach | business, markets | BBC/CBC business, plus the 5protocol market pulse |
| Juno Park | tech, science | BBC tech/science, Ars Technica, NASA |
| Dana Ruiz | consumer | Guardian Money |
| Celeste Storm | weather | Open-Meteo for `GBS_LOCAL_LAT/LON` |
| Flip Torres | traffic | Open511 feed at `GBS_TRAFFIC_OPEN511_URL` (e.g. DriveBC) |
| Lola Sparks | entertainment | BBC Entertainment & Arts, Guardian Culture |
| Troy "Coach" Maddox | sports | BBC Sport, CBC Sports |

A story on a desk nobody owns goes to the show anchor.

## Production → pipeline

| Person | Role in code |
|---|---|
| Margo Kessler, News Director | `editorial/standards.py`: `STANDARDS` sits in every prompt. The sensitivity gate switches persona humour off for death, violence, disaster and similar stories. |
| Priya Sati, Executive Producer | `editorial/rundown.py` plus the open/close rules in `scriptwriter.py`: same-event merge, desk balance, tight open |
| Dex Okafor, Assignment Desk | `roster.presenter_for_desk` |
| Kai Love, AI Anchor Operator | `heygen.speed` per talent in `newsroom.json` (e.g. NOVA 0.9 = "slow the read by 10%") |
| Arbi Ong, Sponsorship Integration | `scriptwriter.write_sponsor_read`: in the presenter's voice, always opens "Sponsored by X.", sponsor claims kept verbatim, falls back to the raw copy if the LLM drifts |
| Owen Pike, Video Editor | `studio/render.compose_cmd`: lower third (name · title), ticker |
| Mina Cho, Digital/Social | `studio/social.py`: 9:16 cuts of real story segments into `public/social/` (not public; for posting) |

## Tone rule

`style` and `sample` shape delivery only. The prompt tells the model to match the energy without reusing the sample line, and personality never changes facts. Serious stories get a straight read whoever presents them.
