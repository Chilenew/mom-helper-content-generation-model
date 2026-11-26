# Ethics: consent, licences, labelling

## 1. Consent

**No real person's face, likeness or voice is generated in this film.**

| Character | Real person? | How they are shown | Voice |
|---|---|---|---|
| The mother ("Emaye") | No: a fictional character inspired by mothers in rural Ethiopia | illustrated, hand-painted style | none of her own: the narration is the child's voice, a prebuilt Gemini TTS voice, not a clone of anyone |
| Selam | No: fictional | from behind / in profile only | none |
| The returning child (narrator) | No: fictional | from behind, or hands only | prebuilt TTS voice |

The storyboard enforces this: every character has `"real_person": false`, and the schema **refuses** any character marked `real_person: true` unless it has a `consent_ref` pointing to a record below.

### If a real person is added later

Record consent **before** generating anything of them, then set `real_person: true` and `consent_ref` in the storyboard.

| consent_ref | Person | Relation | What they agreed to (face / voice / name / words) | How consent was given (recording, message) | Date | Can withdraw by |
|---|---|---|---|---|---|---|
| | | | | | | |

The words in their mouth must be ones they agreed to. Gemini TTS can imitate voices, and this project does not use voice cloning.

## 2. Private data

Several free endpoints may use submitted content to improve their models. The prompts contain **no real names, village names, phone numbers or family details**. The story is a composite.

## 3. Licences of every model and output

| Component | Used for | Licence / terms | Can the output be used commercially? | Checked |
|---|---|---|---|---|
| Gemini 3.8 Flash / Flash TTS (Gemini API, free tier) | script, translation, narration | Gemini API Terms of Service; free-tier content may be used to improve Google products | yes, under the API terms; audio carries a SynthID watermark | _(date)_ |
| FLUX.2 [klein] 4B (Black Forest Labs, via Cloudflare Workers AI) | keyframes | Apache 2.0 for the 4B model _(verify on the model card; the 9B variant has a non-commercial licence)_ | yes _(verify)_ | |
| FLUX.1 [schnell] (fallback only) | keyframes fallback | Apache 2.0 | yes | |
| Wan 2.2 TI2V-5B (Wan-AI) | moving shots | Apache 2.0 | yes | |
| ACE-Step 1.5 (ACE Studio) | score | open weights; per the challenge brief, outputs may be used commercially _(verify the repo licence)_ | yes | |
| FFmpeg | assembly | LGPL/GPL | n/a (tool) | |
| Satie, *Gymnopédie No. 1*, performed by Robin Alciatore ([Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Erik_Satie_-_gymnopedies_-_la_1_ere._lent_et_douloureux.ogg)) | score (current) | composition and recording both marked **public domain** on Commons | yes; credit is not required but is good practice | 2026-11-26 |
| Microsoft neural voices `am-ET-AmehaNeural`, `en-KE-ChilembaNeural` via the `edge-tts` library | narration (current) | Edge read-aloud service used **without an official licence** | **not cleared for public release**: replace with a licensed TTS service or a real recording | 2026-11-26 |
| Ebrima (Microsoft, ships with Windows) | Amharic subtitles, end card | Windows font licence: may be embedded in rendered video | yes | 2026-11-26 |
| DejaVu Sans | subtitles, end card | free font licence (Bitstream Vera derivative) | yes | |
| This repository's code | everything | MIT | — | |

## 4. Style

Prompts describe qualities ("warm hand-painted illustration, soft natural light, earthy browns…") and never name a living artist.

## 5. Labelling plan

- **In the film:** a 3-second end card, *"Made with AI · A story inspired by mothers in rural Ethiopia"*, drawn in code so it is always legible. The schema requires the end card text to contain "AI".
- **On the platform:** the AI-generated content disclosure is switched **on** when posting (TikTok "AI-generated" label / YouTube "Altered or synthetic content" / Meta "AI info").
- **In the post text:** the post states that the film was made with AI models and names them.
- **Provenance:** watermarks embedded by the models (such as SynthID in Gemini audio) are left intact; nothing tries to remove them. Note: re-encoding in FFmpeg may not carry over C2PA metadata attached to source files. _(Record here whether any source file carried C2PA, and what happened to it.)_
