# Understanding by regeneration — closing the half-loop

**2026-07-29. The owner named the fault, and the name is the design:**

> 궁극적으로 atanor가 '이해'할 수 있는 부분이 필요하구나. 말은 잘하는데 자연어를 받았을때 이해를
> 못하는거지? 그래서 지능의 병목이 생겼던거구나. 인간도 자신이 말하면서 그 내용을 바탕으로 또 이해를
> 하는데 atanor는 말할줄만 알았던거니까. 이걸 만들때도 우리의 철학을 지켜.

That last clause is why this document exists before any code.

---

## 1. The asymmetry, proven at code level rather than argued

Two calls, made today, into the organs the system actually runs:

```
generation      ('the player', 'avoid', 'the ghosts')   ->  "the player avoid the ghosts"
                ('the ghosts', 'chase', 'the player')   ->  "the ghosts chase the player"
                ('Sandra', 'travel to', 'the office')   ->  "Sandra travel to the office"

comprehension   "Avoid the ghosts."                     ->  ([], '')
                "The ghosts chase you."                 ->  ([], '')
                "Sandra travelled to the office."       ->  ([], '')
```

The generator is **domain-blind and has no verb limit** — it will say any relation handed to it,
action verbs included. The comprehension path recognises **31 verbs**, every one of them definitional
(`is`, `contains`, `refers`, `describes`, `represents`), and cannot represent an imperative at all
because `builder.py:151` excludes position 0 from the verb search while an imperative's verb *is* at
position 0.

**ATANOR can say "the player avoids the ghosts" and cannot read it back.** The 31-verb ceiling was
never a ceiling on the system; it was a ceiling on the intake, and the outward half was never limited.

### Why this is the bottleneck and not one defect among many

It explains findings from two unrelated lines on the same day:

| observed | explained by |
|---|---|
| fluent generation, multi-hop answering, inner speech | the outward half works and is fed by a graph full of definitions |
| an English rule sentence produces nothing | the inward half does not exist |
| the Atari agent **dies more often than random**, because death pays exactly 0.00 reward across 16 measured deaths | the graph holds static facts and no actions-with-consequences, because the intake only ever admitted `X is a Y` |

One hole. Language has no `avoid`; the game has no cost for being caught.

### And the loop the owner named is literally missing

In humans, production is monitored **through the comprehension system**: Levelt's internal loop routes
the speaker's own forming utterance back through the parser before and as it is spoken, which is why
you catch your own error mid-word. Speaking is a closed loop — you hear yourself and that hearing is
comprehension, not a separate faculty.

ATANOR has been running the outward arc with nothing at the far end. It cannot check what it said
against what it meant, so it cannot learn from its own speech, and its inner voice has been a
broadcast rather than a conversation.

---

## 2. The design: understanding is regeneration

If the system can go **structure → sentence**, then comprehension is the inverse of an organ it
already owns. This is not a new faculty bolted on; it is the existing one run backwards under a
verifier.

```
  a sentence S
      │
      ▼
  PROPOSE   candidate structures Z₁…Z_k        cheap, learned, allowed to be wrong
      │      (entities and relations drawn from the graph's own basis)
      ▼
  REGENERATE  G(Z_i)  using the speaker that already exists
      │
      ▼
  VERIFY    does G(Z_i) reproduce S?           exact, symbolic, cannot be talked into it
      │
      ├── yes for exactly one Z  →  that is the meaning, and it is a GRAPH STRUCTURE
      └── no, or several         →  abstain. Say what was not understood.
```

Three properties follow, and they are the reason this is the right shape rather than a clever one:

**The output is grounded by construction.** The parse is not an embedding or a tree; it is a structure
the graph can hold, because it was drawn from the graph's own relation basis and confirmed by
regeneration. Bone and flesh: the structure is the bone, the sentence is the flesh, and comprehension
is recovering the bone from the flesh.

**Fabrication is impossible, not discouraged.** A structure that does not regenerate the sentence is
rejected by string comparison. There is no path by which a plausible-sounding wrong parse survives.

**It is the project's own formula.** A neural proposer under an exact symbolic verifier is exactly the
AlphaGeometry shape this project already committed to and already uses elsewhere: propose cheaply,
guarantee in the checker.

### Where the training data comes from — the generator labels itself

The hard part of training any parser without an LLM is labels. Here they are free:

> **Generate from a known structure and you have a (sentence, structure) pair whose label is exact by
> construction.** Unlimited, no annotation, no LLM, no pretrained model.

The proposer trains on self-generated pairs; it is **evaluated on human-written text**, which is what
keeps the loop from being circular. Coverage on human text is the only number that counts, and it is
reported against sentences the generator never produced.

### And then the loop closes

Once the inward arc exists, run it on ATANOR's own output. It says something, reads it back, and
compares the recovered structure to the one it meant to express. That single comparison yields:

- **a self-monitor** — a mismatch means it mis-said what it meant
- **a hallucination check that costs nothing** — a sentence whose structure cannot be recovered was
  not grounded in the first place
- **a curriculum** — the sentences it can say but cannot read back are precisely the next thing to
  learn, chosen by the system rather than by me

That is the half-loop the owner identified, closed.

---

## 3. The doctrine check, clause by clause

Explicitly requested, so it is explicit.

| standing rule | how this design stands against it |
|---|---|
| **No LLM, no pretrained sLLM** | the proposer is trained from scratch on pairs ATANOR generates itself; the verifier is symbolic |
| **Rules are training wheels** | the 31-verb lexicon and `builder.py`'s SVO regex are **replaced, not supplemented**. The plan below names the rung at which they are deleted, and deletion is a gate, not an aspiration |
| **Structure over memorisation** | the output is graph structure. Nothing is stored as a surface pattern, and a new verb needs a frame, not an entry |
| **Learned discriminator beats hand rules** | the proposer is learned; the only hand-written part is the verifier, which is a comparison and not a judgement |
| **Speech is generation or silence** | its mirror is the rule of this organ: **understanding is regeneration or abstention.** A sentence that does not regenerate is reported as not understood |
| **Reduce false abstention, never fabricate** | abstention is the floor and not the goal. Coverage on human text is a headline number and a low one is a failure, not a moat |
| **One model, not a mode switch** | one organ for every sentence type. There is no imperative branch — imperatives are just structures whose agent is the addressee |
| **Evidence-only writing** | a recovered structure enters the graph only if it regenerates; otherwise it is quarantined with the sentence attached |
| **Wiring audit: building is not wiring** | this organ is not finished when it passes tests. It is finished when `cgsr/comprehension.py` calls it and the regex path is gone |

---

## 4. The honest limit, stated before it is discovered

**ATANOR will only be able to understand what it can say.** Comprehension coverage is bounded above by
generation coverage, exactly. A sentence whose structure the speaker cannot express is unparseable by
this method, and no amount of proposer training changes that.

This is a real ceiling and it is the correct one to have. It fails by **abstaining**, not by
fabricating — the system says "I did not understand this" rather than inventing a structure — and it
grows by exactly one route: teach the speaker a new construction and comprehension of that
construction follows for free. That coupling is the point, not a side effect. It is also how a person
works: you do not understand a sentence form you cannot produce.

---

## 5. Rungs, and what each may claim

**R1 — measure the inverse on what the speaker already says.**
Generate N sentences from known graph structures, then attempt recovery. This is the easiest possible
case, so it is a **floor, not an achievement**: if the system cannot invert its own output, the method
is wrong and nothing later matters. Reported as coverage and exact-match, with the abstention rate.

**R2 — the proposer.**
Trained on self-generated pairs. Held out and reported: **human-written sentences the generator never
produced**, including imperatives, which the current path cannot represent at all. R2 is where the
claim stops being about self-consistency and starts being about English.

**R3 — replace, then delete.**
`cgsr/comprehension.py` calls the new organ. The 31-verb lexicon and the SVO regex are removed, and
the existing situation-model batteries (bAbI 0.9755 among them) must not regress. **A rung that leaves
the regex in place has not passed**, per the wiring-audit rule.

**R4 — close the self-monitoring loop.**
Run comprehension on ATANOR's own speech and report the mismatch rate. Sentences it can say but cannot
read back become the curriculum.

**R5 — actions.**
Only now does the language layer reach behaviour, and the research for it is in
`ATANOR_action_wiring_from_language_2026-07-29.md`: verbs compile to preferences over predicted
futures, over a closed basis of about twenty image schemas, so that wiring cost stays O(1) in
vocabulary. The falsification test registered there stands: **verbs never seen before must execute**,
judged behaviourally, or the whole thing is a lookup table.

---

## 6. What this document may not be used to claim

Nothing here is a result. R1–R5 are unbuilt. What is measured is: the generator's output on four
action triples, the comprehension path's empty output on the same content, the 31-entry verb lexicon,
the two lines in `builder.py`, and today's Atari figures (deaths 12.4 vs random 11.0 per thousand
steps; death reward 0.00 across 16 deaths). Everything else is a plan, and a plan is not evidence.
