# Design

## 1. Audience and intent (written before generating anything, 25 November 2026)

**Who watches:** young Ethiopians who live in Addis Ababa, other cities, or abroad, whose parents live in the countryside and cannot read or write. They watch on a phone, vertically, in a social feed, often with the sound low or off. That's why subtitles are burned in.

**Where:** TikTok / Instagram Reels / YouTube Shorts (9:16), and YouTube or family WhatsApp groups (16:9).

**What they should feel at the end:** tenderness toward a parent far away, and the small push to **send their mother a voice message today**.

**Logline:** A mother in a rural village who cannot read keeps every letter from her child in a tin box, until the child comes home and gives her a way to answer in her own voice.

**Why this story:** _(write 2–3 sentences in your own words: what in your own family this comes from, and why it matters to you. The interview and the public post will ask.)_

## 2. Design decisions

| Decision | Reason |
|---|---|
| One face to keep consistent (the mother) | Selam is seen only from behind or in profile, and the returning child is never shown; fewer faces means fewer consistency failures |
| Hand-painted style, not photoreal | Hides small face drift between shots and avoids realistic depictions of real people |
| The tin box returns at shots 7 and 11 | A motif gives an 80-second film a shape: it means "waiting" the first time and "an answer" the second |
| No readable text in any image | Image models garble writing; letters stay folded and the phone screen shows only an icon |
| Slow, single movements | Wan 2.2 is most stable with one gentle motion; it also suits the patient tone |
| Narration in Amharic, subtitles in English | Amharic is the mother's voice and the audience's home language; English widens the audience |
| Quiet masinko/krar score that lifts at the return | Leaves room for the voice; the lift at shot 9 marks the turning point |

## 3. Every shot has a reason

| Shot | Size | What we see | Reason |
|---|---|---|---|
| s01 | extreme wide | the village and the warka tree at dawn | establish the place where news arrives |
| s02 | medium | mother in the doorway holding an envelope | introduce her, and the problem: she cannot read |
| s03 | close-up | her hands turning the envelope | show how precious the letters are |
| s04 | wide | she walks to the tree; Selam waits | introduce Selam and the ritual place |
| s05 | medium | Selam reads aloud, mother listens | the ritual that connects mother and child |
| s06 | close-up | mother's face, eyes closed, smiling | emotional centre: she hears her child through another voice |
| s07 | close-up | the tin box of letters opens | reveal the motif |
| s08 | medium | alone at night, box on her lap | turning point: her love could only travel one way |
| s09 | wide | the child walks up the path at sunset | the return |
| s10 | extreme close-up | her finger on the phone, a younger hand guiding | the solution: one button gives her a voice |
| s11 | close-up | the phone placed in the box with the letters | payoff: now her voice travels back |

## 4. User test 1: the radio cut

**What was shown:** `outputs/radio_cut/radio_cut.mp4` (narration + placeholder music on black, English subtitles), storyboard version `0.1.0`.
**How:** _(in person / Slack / WhatsApp)_ **Date:** _(fill in)_

Questions asked:
1. In one sentence, what is this story about?
2. What did you feel at the end?
3. Was any moment confusing, too fast or too slow?
4. (Amharic speakers) Did any word sound wrong or unnatural?

| # | Who (relation to audience) | Q1: story in one sentence | Q2: feeling at the end | Q3/Q4: confusing, pace, pronunciation |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |

**What I learned:** _(patterns across the answers)_

**What I changed in the storyboard** (bump `version` to `0.2.0`):

| Change | Because tester(s) said | Shot(s) |
|---|---|---|
| | | |

## 5. User test 2: the near-final cut

**What was shown:** `outputs/final/film_9x16.mp4`, storyboard version _(x.y.z)_. **Date:** _(fill in)_

| # | Who | Story in one sentence | Feeling at the end | What didn't work |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |

**What I changed** (bump `version`):

| Change | Because | Shot(s) |
|---|---|---|
| | | |

## 6. Storyboard version history

| Version | Date | What changed | Why |
|---|---|---|---|
| 0.1.0 | 2026-11-25 | first full storyboard, 11 shots, 83 s | from the story brief |
