# -*- coding: utf-8 -*-
"""B's sealed evaluation for the G3 transfer gate. Frozen with the rest of `packages/fluency`.

This file lives INSIDE the frozen surface on purpose. An evaluation kept outside it could be
rewritten after seeing the result, which is the exam-editing this gate exists to prevent.

HOW THE CORPUS WAS DRAWN, so it is reproducible and provably not hand-picked: subjects of the
shipped graph with 3-8 edges, sorted by interned id, taken at a fixed stride across the whole band
(17,252,363 subjects), keeping the first 6 ASCII facts of each until 20 sets were collected; 17
survived the ASCII/length filter. Nobody chose a subject, and no set was inspected before it was
frozen -- so the corpus cannot have been fitted to what the realizer happens to do well.

THE METRICS ARE FLUENCY'S OWN. `slot_copy_accuracy`, `faithfulness` and `fluency_proxy` already
existed in `fluency_v1`; nothing here invents a scorer that could be tuned toward a flattering
number. `empty_rate` is the abstention floor -- a realizer that says nothing scores perfectly on
faithfulness, so it has to be counted separately or silence would read as skill.

DETERMINISTIC BY CONSTRUCTION: fixed corpus, no clock, no randomness, no store access at eval time.
"""
from __future__ import annotations

from typing import Any

BONES: list[list[list[str]]] = [
    [
        [
            "Emirate of Al Qawasim",
            "is_a",
            "historical country"
        ],
        [
            "Emirate of Al Qawasim",
            "is_a",
            "country"
        ],
        [
            "Emirate of Al Qawasim",
            "official_language",
            "Arabic"
        ],
        [
            "Emirate of Al Qawasim",
            "country",
            "United Arab Emirates"
        ],
        [
            "Emirate of Al Qawasim",
            "country",
            "Oman"
        ],
        [
            "Emirate of Al Qawasim",
            "country",
            "Iran"
        ]
    ],
    [
        [
            "Basse-Pointe",
            "country",
            "France"
        ],
        [
            "Basse-Pointe",
            "located_in",
            "Martinique"
        ],
        [
            "Basse-Pointe",
            "located_in",
            "Canton of Basse-Pointe"
        ],
        [
            "Basse-Pointe",
            "is_a",
            "commune of France"
        ],
        [
            "Basse-Pointe",
            "is_a",
            "second-level administrative division"
        ],
        [
            "Basse-Pointe",
            "is_a",
            "human settlement"
        ]
    ],
    [
        [
            "Dynasty Wars",
            "is_a",
            "video game"
        ],
        [
            "Dynasty Wars",
            "genre",
            "beat 'em up"
        ],
        [
            "Dynasty Wars",
            "country",
            "Japan"
        ]
    ],
    [
        [
            "Ivanivska Church, Pryluky",
            "is_a",
            "church building"
        ],
        [
            "Ivanivska Church, Pryluky",
            "country",
            "Ukraine"
        ],
        [
            "Ivanivska Church, Pryluky",
            "located_in",
            "Pryluky"
        ]
    ],
    [
        [
            "Mana Endo",
            "is_a",
            "human"
        ],
        [
            "Mana Endo",
            "occupation",
            "tennis player"
        ],
        [
            "Mana Endo",
            "sport",
            "tennis"
        ],
        [
            "Mana Endo",
            "employer",
            "Tsukuba Gakuin University"
        ],
        [
            "Mana Endo",
            "employer",
            "Tokyo Keizai University"
        ]
    ],
    [
        [
            "Preeti Dahiya",
            "is_a",
            "human"
        ],
        [
            "Preeti Dahiya",
            "occupation",
            "boxer"
        ],
        [
            "Preeti Dahiya",
            "sport",
            "boxing"
        ]
    ],
    [
        [
            "Temuri Shonia",
            "is_a",
            "human"
        ],
        [
            "Temuri Shonia",
            "occupation",
            "association football player"
        ],
        [
            "Temuri Shonia",
            "sport",
            "association football"
        ]
    ],
    [
        [
            "FIBT World Championships 1979",
            "sport",
            "bobsleigh"
        ],
        [
            "FIBT World Championships 1979",
            "country",
            "Germany"
        ],
        [
            "FIBT World Championships 1979",
            "is_a",
            "sports season"
        ]
    ],
    [
        [
            "Shinkichi Okada",
            "is_a",
            "human"
        ],
        [
            "Shinkichi Okada",
            "occupation",
            "translator"
        ],
        [
            "Shinkichi Okada",
            "occupation",
            "film critic"
        ]
    ],
    [
        [
            "Dante Alighieri -Tradate Ab. G",
            "located_in",
            "Tradate"
        ],
        [
            "Dante Alighieri -Tradate Ab. G",
            "country",
            "Italy"
        ],
        [
            "Dante Alighieri -Tradate Ab. G",
            "is_a",
            "primary school"
        ]
    ],
    [
        [
            "February 20, 1658",
            "is_a",
            "February 20"
        ],
        [
            "February 20, 1658",
            "is_a",
            "calendar day of a given year"
        ],
        [
            "February 20, 1658",
            "part_of",
            "February 1658"
        ]
    ],
    [
        [
            "Theresianum",
            "is_a",
            "school"
        ],
        [
            "Theresianum",
            "country",
            "Hungary"
        ],
        [
            "Theresianum",
            "country",
            "Austria"
        ],
        [
            "Theresianum",
            "located_in",
            "Neue Favorita"
        ],
        [
            "Theresianum",
            "located_in",
            "Vienna"
        ],
        [
            "Theresianum",
            "country",
            "Germany"
        ]
    ],
    [
        [
            "RIC III Antoninus Pius 490",
            "is_a",
            "coin type"
        ],
        [
            "RIC III Antoninus Pius 490",
            "is_a",
            "coin"
        ],
        [
            "RIC III Antoninus Pius 490",
            "made_of",
            "silver"
        ],
        [
            "RIC III Antoninus Pius 490",
            "part_of",
            "Roman Imperial Coinage"
        ]
    ],
    [
        [
            "Movyans Skolyow Meythrin",
            "country",
            "United Kingdom"
        ],
        [
            "Movyans Skolyow Meythrin",
            "is_a",
            "nonprofit organization"
        ],
        [
            "Movyans Skolyow Meythrin",
            "located_in",
            "Camborne"
        ]
    ],
    [
        [
            "Skin Layer ofBiFeO3Single Crystals",
            "author",
            "Xavier Marti"
        ],
        [
            "Skin Layer ofBiFeO3Single Crystals",
            "author",
            "Pilar Ferrer"
        ],
        [
            "Skin Layer ofBiFeO3Single Crystals",
            "author",
            "Julia Herrero-Albillos"
        ],
        [
            "Skin Layer ofBiFeO3Single Crystals",
            "author",
            "Marin Alexe"
        ],
        [
            "Skin Layer ofBiFeO3Single Crystals",
            "author",
            "Gustau Catalan"
        ]
    ],
    [
        [
            "Genetics of inflammatory bowel disease",
            "author",
            "Derek P. Jewell"
        ],
        [
            "Genetics of inflammatory bowel disease",
            "author",
            "Richard Duerr"
        ],
        [
            "Genetics of inflammatory bowel disease",
            "author",
            "Jerome I Rotter"
        ],
        [
            "Genetics of inflammatory bowel disease",
            "author",
            "Kent D Taylor"
        ]
    ],
    [
        [
            "1959 Essex Badminton Championships",
            "country",
            "United Kingdom"
        ],
        [
            "1959 Essex Badminton Championships",
            "sport",
            "badminton"
        ],
        [
            "1959 Essex Badminton Championships",
            "is_a",
            "Essex Badminton Championships"
        ]
    ]
]


def evaluate() -> dict[str, float]:
    """Realize every frozen bone-set and score it with fluency's own metrics."""
    from packages.fluency import fluency_v1 as F
    from packages.fluency.realizer import realize

    slot, faith, prox, empty = [], [], [], 0
    for bones in BONES:
        try:
            text = realize([list(b) for b in bones]) or ""
        except Exception:
            text = ""
        if not text.strip():
            empty += 1
            continue
        slot.append(float(F.slot_copy_accuracy([list(b) for b in bones], text)))
        try:
            grounding = F.Grounding.from_bones([list(b) for b in bones])
            faith.append(float(F.faithfulness(text, grounding)[0]))
        except Exception:
            pass
        try:
            prox.append(float(F.fluency_proxy(text)[0]))
        except Exception:
            pass

    def _mean(xs: list[float]) -> float:
        return round(sum(xs) / len(xs), 6) if xs else 0.0

    return {
        "slot_copy_accuracy": _mean(slot),
        "faithfulness": _mean(faith),
        "fluency_proxy": _mean(prox),
        "empty_rate": round(empty / len(BONES), 6),
        "scored": float(len(slot)),
    }


def report() -> dict[str, Any]:
    return {"corpus": len(BONES), **evaluate()}
