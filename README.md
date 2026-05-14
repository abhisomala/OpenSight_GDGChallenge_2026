# README
Replace everything from `# OpenSight` through the end of `## The Problem` header
with the text below. Everything after that stays as-is.

---

# OpenSight

**The AI that remembers so you don't have to.**

> OpenSight is a multi-agent voice assistant for visually impaired users that builds context across tasks automatically — so users speak one sentence per step and never repeat themselves. Say *"find me a supplement for that"* and OpenSight already knows what *that* is. No existing screen reader, voice assistant, or browser agent does this.

*Google Developer Groups on Campus Solution Challenge 2026 · SDG 10: Reduced Inequalities · SDG 3: Good Health and Well-Being*

---

## What makes OpenSight different

Every other accessibility tool treats each query as a blank slate.

NVDA and JAWS read interfaces linearly — they have no concept of what you were doing five seconds ago. Apple VoiceOver is mobile-first and cannot navigate desktop web flows autonomously. ChatGPT can answer questions but cannot open a browser, navigate search results, and carry the context of that search into a completely different task without being told every step explicitly.

OpenSight does all three — and it does them with a single sentence per step.

When you ask OpenSight to find research on omega-3 and brain health, it opens Google Scholar and finds papers. When you then say *"find me a supplement for that under $30,"* OpenSight already knows what *that* means. It pulls the research context forward automatically, opens Amazon, and returns results — no second explanation required. This cross-agent memory is the core architectural insight: a shared memory layer that spans every agent, so context built in one task is available to every task that follows.

This is not a feature. It is the design principle the entire system is built around.

**2.2 billion people** worldwide have a vision impairment (WHO, 2023). The tools built to help them treat every task as a fresh start. OpenSight does not.

---

## The Problem

...  *(keep the existing Problem section unchanged from here)*

---
---
---

# Video script — first 30 seconds
Replace your current opening narration with this. Designed to be spoken over
a screen recording showing the UI orb idle, then activating.

---

**[0:00 — UI idle, orb dim]**

"Every screen reader in use today has the same fundamental problem: it forgets.

Finish a research search. Switch to shopping. You start over from zero.

OpenSight is built around one idea: the system should remember, so you don't have to."

**[0:12 — wake word fires, orb lights up]**

"Say 'OpenSight' — and it's ready."

**[0:15 — first query spoken aloud, Scholar tab opens]**

*"Find me research on omega-3 and brain health."*

"One sentence. Google Scholar opens. Papers load."

**[0:21 — second query spoken, Amazon opens automatically]**

*"Find me a supplement for that under $30."*

"OpenSight already knows what *that* means. No repetition. No re-explaining. Amazon
opens with a search built from the research context it just built."

**[0:30 — cut to timer graphic: 28 seconds elapsed]**

"A task that takes a first-time screen reader user ten minutes — done in under thirty seconds."

---

## Notes on delivery

- Pause one full beat after *"it forgets"* — let it land before moving on.
- The second query (*"find me a supplement for that"*) is the money moment. Slow
  down slightly on *"that"* so viewers register that no context was re-stated.
- The timer graphic at 0:30 is optional but effective — it makes the 10x claim
  concrete and visual rather than just a stat in a README.