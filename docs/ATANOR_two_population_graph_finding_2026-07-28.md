# The shipped graph is two populations, and entity resolution across them is not currently possible

**2026-07-28.** Investigating whether surface-form contamination in complement queries
("which countries have no capital city?") could be filtered structurally rather than by
correcting spellings one at a time.

**Conclusion: do not build entity resolution.** The signals required do not exist in the graph.
The contamination that motivated this is also already gone from the live answer, for a structural
reason worth recording.

## What the graph actually looks like

`is_a country` and `is_a Country` are two type labels over overlapping but distinct populations:

| population | count | examples | connectivity |
|---|---|---|---|
| dual-typed (both labels) | 182 | `United Kingdom`, `Mexico`, `Thailand` | rich |
| `Country`-only | 195 | `Taiwan`, `Soviet Union`, `Baekje`, `State of Palestine` | rich |
| `country`-only | 190 | `france`, `japan`, `interior`, `power`, `countryside` | sparse, orphaned |

The lowercase-only members are ConceptNet residue. They are not merely spelled differently -- they
live in a **disjoint subgraph**. Measured neighbourhood contents:

```
france  points at:  europe, beaches, eiffel tower, about 60 million inhabitants
France  points at:  Belgium, Dunkirk, Briançon, Cleveland Museum of Art
shared           :  (empty)
```

Lowercase nodes point at lowercase nodes; capitalised nodes point at capitalised nodes. The two
halves share a term dictionary and almost nothing else.

## Why entity resolution cannot be built on this

Three candidate signals were measured, each against a negative control. Two failed outright:

| signal | same-entity pairs | control pairs | verdict |
|---|---|---|---|
| `alias` predicate (905,622 edges) | 1 of 45 reachable | — | **2% coverage** |
| neighbourhood overlap | **0.000** | 0.000 | **no signal at all** |
| type-level member overlap | 0.29–0.94 | 0.00–0.15 | works, but types only |

Neighbourhood overlap fails not because the metric is wrong but because the neighbourhoods are
themselves case-split: there is no bridge to find. Any resolver built here would be asserting
identity on no evidence -- fabrication with extra steps.

A relation-PROFILE similarity was also tried and rejected: it scores 0.778 even for
`country`/`Protein`, because every entity carries `is_a` and `defined_as`, so the universal
relations drown the discriminative ones. This is the same trap as coverage-maximisation selecting
`is_a` (see the scene composer's selection ladder) -- **a signal everything has cannot separate
anything.**

## Why the live answer is already correct

The composer selects the head type by pairing coverage. On this data that selects `Country`, whose
population is the well-connected one, and the orphaned lowercase members never enter the scene.
Measured: `alias_suspects` on the `Country` reading is **0** (on the `country` reading it is 53).

The remaining 45 members of `Country` lacking a `capital` edge are **not contamination** -- they
are correct:

```
Assyria, Hittites, Huns, Kassites, Ebla, Bernicia, Crown of Aragon,      (ancient states)
Axis powers, Central Powers, Arab League, Commonwealth of Nations,        (alliances/unions)
European Economic Community, Adélie Land, Bassas da India, Holy See      (territories/other)
```

These genuinely have no capital, or no capital in the modern sense. The earlier "105 unexplained
residue" figure came from the `country` (lowercase) reading, which the composer no longer picks.

## What would actually be needed

Not a cleverer similarity metric -- a **join**. Either an ingest-time alignment (Wikidata QIDs to
ConceptNet URIs, which the upstream sources support and this store discarded), or a decision to
retire the orphaned ConceptNet population for types where a richer Wikidata population exists.
Both are ingest/promotion work under the operator gate, not answer-path work.

Until then the honest position is the current one: prefer the connected population, report
`alias_suspects` when a complement is contaminated, and abstain rather than assert an identity the
graph does not hold.
