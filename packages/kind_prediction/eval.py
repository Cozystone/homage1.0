# -*- coding: utf-8 -*-
"""Domain B for the V7-3 transfer gate: predict an entity's KIND from its behaviour alone.

This package exists to be FROZEN. Plan v6 §6 made one criterion mandatory after the fluency seal
turned out to have no mechanistic channel: B is admissible only when its evaluation path PROVABLY
traverses the substrate the A-side work will change. `evaluate` below calls
`packages.substrate.decisive_kind` directly, so the channel is not a plausibility argument -- it is
the call stack.

WHY THIS IS A DIFFERENT DOMAIN AND NOT A1c POINTED AT NEW INPUTS. It must SHARE the substrate (or
there is no channel) and differ in everything else (or it is the same test):

  task          classify a WHOLE ENTITY against every profiled kind -- A1c attributes single EDGES
                of one merged node to the kinds that node declares
  candidates    all eight profiled kinds -- A1c's candidates come from the node's own `is_a` edges
  ground truth  the graph's own `is_a`, which the input has been stripped of -- A1c has no labels
                at all and is scored by hand-checked correctness
  metric        accuracy over predictions plus coverage -- A1c is scored per placement

HOW THE CORPUS WAS DRAWN, so it is reproducible and provably not hand-picked: for each kind, the
entities of that kind sorted by interned id, taken at a fixed stride across the whole extension,
keeping the first 12 with at least 2 ASCII facts. `is_a` is STRIPPED from every entity, because it
is the answer -- leaving it in would let the classifier read the label off the input.

The kind prevalences are the graph's, computed by `type_affinity.type_profiles` and frozen here so
the evaluation cannot drift when the shipped store changes. Predicates below 2% prevalence are
dropped as noise.

DETERMINISTIC: fixed corpus, fixed prevalences, no clock, no randomness, no store access at eval
time.
"""
from __future__ import annotations

from typing import Any

CORPUS: list[dict[str, Any]] = [
 {
  "entity": "tell",
  "kind": "archaeological site",
  "facts": [
   [
    "tell",
    "antonym",
    "ask"
   ],
   [
    "tell",
    "manner_of",
    "guess"
   ],
   [
    "tell",
    "manner_of",
    "inform"
   ],
   [
    "tell",
    "alias",
    "william tell"
   ],
   [
    "tell",
    "alias",
    "narrate"
   ],
   [
    "tell",
    "alias",
    "recount"
   ],
   [
    "tell",
    "alias",
    "advise"
   ],
   [
    "tell",
    "alias",
    "count"
   ],
   [
    "tell",
    "alias",
    "disclose"
   ],
   [
    "tell",
    "alias",
    "grass up"
   ],
   [
    "tell",
    "alias",
    "distinguish"
   ],
   [
    "tell",
    "alias",
    "assure"
   ]
  ]
 },
 {
  "entity": "Rosenburg",
  "kind": "archaeological site",
  "facts": [
   [
    "Rosenburg",
    "defined_as",
    "A surname from German, variant of Rosenberg"
   ],
   [
    "Rosenburg",
    "defined_as",
    "plural of picosignal"
   ],
   [
    "Rosenburg",
    "country",
    "Canada"
   ],
   [
    "Rosenburg",
    "country",
    "Germany"
   ],
   [
    "Rosenburg",
    "located_in",
    "Stadtbezirk Bonn"
   ],
   [
    "Rosenburg",
    "located_in",
    "Kessenich"
   ],
   [
    "Rosenburg",
    "country",
    "Switzerland"
   ],
   [
    "Rosenburg",
    "located_in",
    "Herisau"
   ],
   [
    "Rosenburg",
    "country",
    "Austria"
   ],
   [
    "Rosenburg",
    "located_in",
    "Rosenburg-Mold"
   ],
   [
    "Rosenburg",
    "country",
    "United States"
   ],
   [
    "Rosenburg",
    "located_in",
    "Platte County"
   ]
  ]
 },
 {
  "entity": "Blanchette Archeological Site",
  "kind": "archaeological site",
  "facts": [
   [
    "Blanchette Archeological Site",
    "country",
    "United States"
   ],
   [
    "Blanchette Archeological Site",
    "located_in",
    "Florida"
   ]
  ]
 },
 {
  "entity": "Eutresis",
  "kind": "archaeological site",
  "facts": [
   [
    "Eutresis",
    "country",
    "Greece"
   ],
   [
    "Eutresis",
    "author",
    "Oliver Thomas Pilkington Kirwan Dickinson"
   ],
   [
    "Eutresis",
    "located_in",
    "Thiva Municipality"
   ]
  ]
 },
 {
  "entity": "La Campana",
  "kind": "archaeological site",
  "facts": [
   [
    "La Campana",
    "country",
    "Mexico"
   ],
   [
    "La Campana",
    "located_in",
    "Chihuahua Municipality"
   ],
   [
    "La Campana",
    "located_in",
    "Lerdo Municipality"
   ],
   [
    "La Campana",
    "country",
    "Cuba"
   ],
   [
    "La Campana",
    "country",
    "United States"
   ],
   [
    "La Campana",
    "country",
    "Spain"
   ],
   [
    "La Campana",
    "located_in",
    "Checa"
   ],
   [
    "La Campana",
    "country",
    "Nicaragua"
   ],
   [
    "La Campana",
    "located_in",
    "Rivas Department"
   ],
   [
    "La Campana",
    "located_in",
    "San Juan del Sur"
   ],
   [
    "La Campana",
    "country",
    "Italy"
   ],
   [
    "La Campana",
    "located_in",
    "Montefiore dell'Aso"
   ]
  ]
 },
 {
  "entity": "Petroglyph National Monument",
  "kind": "archaeological site",
  "facts": [
   [
    "Petroglyph National Monument",
    "country",
    "United States"
   ],
   [
    "Petroglyph National Monument",
    "located_in",
    "Bernalillo County"
   ]
  ]
 },
 {
  "entity": "Trinchera Cave Archeological District",
  "kind": "archaeological site",
  "facts": [
   [
    "Trinchera Cave Archeological District",
    "country",
    "United States"
   ],
   [
    "Trinchera Cave Archeological District",
    "located_in",
    "Colorado"
   ]
  ]
 },
 {
  "entity": "Combe Ditch, linear dyke",
  "kind": "archaeological site",
  "facts": [
   [
    "Combe Ditch, linear dyke",
    "country",
    "United Kingdom"
   ],
   [
    "Combe Ditch, linear dyke",
    "located_in",
    "Charlton Marshall"
   ]
  ]
 },
 {
  "entity": "CERRO DEL ROMERO",
  "kind": "archaeological site",
  "facts": [
   [
    "CERRO DEL ROMERO",
    "country",
    "Argentina"
   ],
   [
    "CERRO DEL ROMERO",
    "part_of",
    "BADACOR"
   ]
  ]
 },
 {
  "entity": "Ancient settlement No 2998, Zhytomyr",
  "kind": "archaeological site",
  "facts": [
   [
    "Ancient settlement No 2998, Zhytomyr",
    "country",
    "Ukraine"
   ],
   [
    "Ancient settlement No 2998, Zhytomyr",
    "located_in",
    "Zhytomyr"
   ]
  ]
 },
 {
  "entity": "Comitium of Cosa",
  "kind": "archaeological site",
  "facts": [
   [
    "Comitium of Cosa",
    "country",
    "Italy"
   ],
   [
    "Comitium of Cosa",
    "located_in",
    "Ansedonia"
   ],
   [
    "Comitium of Cosa",
    "part_of",
    "Cosa"
   ]
  ]
 },
 {
  "entity": "precision",
  "kind": "encyclopedia article",
  "facts": [
   [
    "precision",
    "antonym",
    "imprecision"
   ],
   [
    "precision",
    "alias",
    "accuracy"
   ],
   [
    "precision",
    "alias",
    "preciseness"
   ],
   [
    "precision",
    "alias",
    "exactitude"
   ],
   [
    "precision",
    "alias",
    "exactness"
   ],
   [
    "precision",
    "defined_as",
    "The ability of a measurement to be reproduced consistently"
   ],
   [
    "precision",
    "alias",
    "nicety"
   ],
   [
    "precision",
    "alias",
    "repeatability"
   ],
   [
    "precision",
    "alias",
    "reproducibility"
   ],
   [
    "precision",
    "defined_as",
    "Used for exact or precise measurement"
   ],
   [
    "precision",
    "defined_as",
    "Made, or characterized by accuracy"
   ],
   [
    "precision",
    "defined_as",
    "compound"
   ]
  ]
 },
 {
  "entity": "Chen Tong",
  "kind": "encyclopedia article",
  "facts": [
   [
    "Chen Tong",
    "occupation",
    "rebel"
   ],
   [
    "Chen Tong",
    "occupation",
    "farmer"
   ],
   [
    "Chen Tong",
    "occupation",
    "businessperson"
   ],
   [
    "Chen Tong",
    "occupation",
    "physicist"
   ],
   [
    "Chen Tong",
    "employer",
    "Institute of Acoustics"
   ],
   [
    "Chen Tong",
    "occupation",
    "military officer"
   ],
   [
    "Chen Tong",
    "part_of",
    "365 Deities"
   ]
  ]
 },
 {
  "entity": "Kukryniksy",
  "kind": "encyclopedia article",
  "facts": [
   [
    "Kukryniksy",
    "genre",
    "alternative rock"
   ],
   [
    "Kukryniksy",
    "genre",
    "post-punk"
   ],
   [
    "Kukryniksy",
    "genre",
    "punk rock"
   ],
   [
    "Kukryniksy",
    "genre",
    "gothic rock"
   ],
   [
    "Kukryniksy",
    "country",
    "Russia"
   ],
   [
    "Kukryniksy",
    "occupation",
    "poster artist"
   ],
   [
    "Kukryniksy",
    "occupation",
    "caricaturist"
   ],
   [
    "Kukryniksy",
    "occupation",
    "designer"
   ],
   [
    "Kukryniksy",
    "has_a",
    "Mikhail Kupriyanov"
   ],
   [
    "Kukryniksy",
    "has_a",
    "Porfiri Krylov"
   ],
   [
    "Kukryniksy",
    "has_a",
    "Nikolay Sokolov"
   ],
   [
    "Kukryniksy",
    "country",
    "Soviet Union"
   ]
  ]
 },
 {
  "entity": "dune",
  "kind": "hill",
  "facts": [
   [
    "dune",
    "antonym",
    "dyke"
   ],
   [
    "dune",
    "alias",
    "sand dune"
   ],
   [
    "dune",
    "alias",
    "sand-dune"
   ],
   [
    "dune",
    "alias",
    "fuel"
   ],
   [
    "dune",
    "alias",
    "send"
   ]
  ]
 },
 {
  "entity": "Duppas Hill",
  "kind": "hill",
  "facts": [
   [
    "Duppas Hill",
    "country",
    "United Kingdom"
   ],
   [
    "Duppas Hill",
    "located_in",
    "London Borough of Croydon"
   ],
   [
    "Duppas Hill",
    "located_in",
    "Croydon"
   ]
  ]
 },
 {
  "entity": "Sese",
  "kind": "hill",
  "facts": [
   [
    "Sese",
    "country",
    "Botswana"
   ],
   [
    "Sese",
    "located_in",
    "Southern District"
   ],
   [
    "Sese",
    "country",
    "Indonesia"
   ],
   [
    "Sese",
    "located_in",
    "North Dampal"
   ],
   [
    "Sese",
    "country",
    "Zimbabwe"
   ],
   [
    "Sese",
    "located_in",
    "Masvingo Province"
   ],
   [
    "Sese",
    "country",
    "Uganda"
   ],
   [
    "Sese",
    "located_in",
    "Mayuge District"
   ],
   [
    "Sese",
    "located_in",
    "Kagadi"
   ],
   [
    "Sese",
    "located_in",
    "Busirabo"
   ],
   [
    "Sese",
    "located_in",
    "Kagadi District"
   ],
   [
    "Sese",
    "country",
    "Malawi"
   ]
  ]
 },
 {
  "entity": "The Peak",
  "kind": "hill",
  "facts": [
   [
    "The Peak",
    "country",
    "Australia"
   ],
   [
    "The Peak",
    "located_in",
    "Queensland"
   ],
   [
    "The Peak",
    "country",
    "Zimbabwe"
   ],
   [
    "The Peak",
    "located_in",
    "Mashonaland Central Province"
   ],
   [
    "The Peak",
    "country",
    "United States"
   ],
   [
    "The Peak",
    "located_in",
    "Rappahannock County"
   ],
   [
    "The Peak",
    "located_in",
    "Cooper"
   ],
   [
    "The Peak",
    "located_in",
    "Carrathool Shire"
   ],
   [
    "The Peak",
    "country",
    "New Zealand"
   ],
   [
    "The Peak",
    "located_in",
    "Alleghany County"
   ],
   [
    "The Peak",
    "country",
    "South Africa"
   ],
   [
    "The Peak",
    "located_in",
    "Mpumalanga"
   ]
  ]
 },
 {
  "entity": "Ospehaug",
  "kind": "hill",
  "facts": [
   [
    "Ospehaug",
    "country",
    "Norway"
   ],
   [
    "Ospehaug",
    "located_in",
    "Kviteseid Municipality"
   ],
   [
    "Ospehaug",
    "located_in",
    "Fjaler Municipality"
   ],
   [
    "Ospehaug",
    "located_in",
    "Hyllestad Municipality"
   ],
   [
    "Ospehaug",
    "located_in",
    "Sveio Municipality"
   ],
   [
    "Ospehaug",
    "located_in",
    "Sogndal Municipality"
   ]
  ]
 },
 {
  "entity": "Sveisarkal",
  "kind": "hill",
  "facts": [
   [
    "Sveisarkal",
    "country",
    "Norway"
   ],
   [
    "Sveisarkal",
    "located_in",
    "Namdalseid Municipality"
   ],
   [
    "Sveisarkal",
    "located_in",
    "Namsos Municipality"
   ]
  ]
 },
 {
  "entity": "Kirjulen",
  "kind": "hill",
  "facts": [
   [
    "Kirjulen",
    "country",
    "Norway"
   ],
   [
    "Kirjulen",
    "located_in",
    "Re Municipality"
   ]
  ]
 },
 {
  "entity": "Mesa La Caballada",
  "kind": "hill",
  "facts": [
   [
    "Mesa La Caballada",
    "country",
    "Mexico"
   ],
   [
    "Mesa La Caballada",
    "located_in",
    "Coahuila"
   ]
  ]
 },
 {
  "entity": "Draa el Kelb",
  "kind": "hill",
  "facts": [
   [
    "Draa el Kelb",
    "country",
    "Algeria"
   ],
   [
    "Draa el Kelb",
    "located_in",
    "Batna Province"
   ]
  ]
 },
 {
  "entity": "Gliza",
  "kind": "hill",
  "facts": [
   [
    "Gliza",
    "country",
    "Serbia"
   ],
   [
    "Gliza",
    "located_in",
    "Serbia"
   ]
  ]
 },
 {
  "entity": "Nowhatta",
  "kind": "human settlement",
  "facts": [
   [
    "Nowhatta",
    "country",
    "India"
   ],
   [
    "Nowhatta",
    "located_in",
    "Srinagar district"
   ]
  ]
 },
 {
  "entity": "Cummings",
  "kind": "human settlement",
  "facts": [
   [
    "Cummings",
    "defined_as",
    "A surname"
   ],
   [
    "Cummings",
    "defined_as",
    "A place name:"
   ],
   [
    "Cummings",
    "defined_as",
    "A township in Lycoming County, Pennsylvania, United States"
   ],
   [
    "Cummings",
    "defined_as",
    "plural of spudding"
   ],
   [
    "Cummings",
    "defined_as",
    "plural of Weiher"
   ],
   [
    "Cummings",
    "defined_as",
    "plural of Neandertaler"
   ],
   [
    "Cummings",
    "defined_as",
    "plural of Platten"
   ],
   [
    "Cummings",
    "defined_as",
    "plural of Weinberg"
   ],
   [
    "Cummings",
    "country",
    "United States"
   ],
   [
    "Cummings",
    "located_in",
    "Traill County"
   ],
   [
    "Cummings",
    "located_in",
    "California"
   ],
   [
    "Cummings",
    "located_in",
    "Mendocino County"
   ]
  ]
 },
 {
  "entity": "Casazza",
  "kind": "human settlement",
  "facts": [
   [
    "Casazza",
    "defined_as",
    "A surname"
   ],
   [
    "Casazza",
    "country",
    "Italy"
   ],
   [
    "Casazza",
    "located_in",
    "Rosolini"
   ],
   [
    "Casazza",
    "located_in",
    "Occhiobello"
   ],
   [
    "Casazza",
    "located_in",
    "Province of Bergamo"
   ],
   [
    "Casazza",
    "located_in",
    "Brescia"
   ],
   [
    "Casazza",
    "located_in",
    "Sermide e Felonica"
   ],
   [
    "Casazza",
    "located_in",
    "Monticelli d'Ongina"
   ],
   [
    "Casazza",
    "located_in",
    "Borriana"
   ],
   [
    "Casazza",
    "located_in",
    "Cairo Montenotte"
   ]
  ]
 },
 {
  "entity": "West River",
  "kind": "human settlement",
  "facts": [
   [
    "West River",
    "defined_as",
    "A river in Prince Edward Island, Canada"
   ],
   [
    "West River",
    "defined_as",
    "plural of Toya"
   ],
   [
    "West River",
    "defined_as",
    "plural of Revette"
   ],
   [
    "West River",
    "defined_as",
    "plural of Stucke"
   ],
   [
    "West River",
    "country",
    "United States"
   ],
   [
    "West River",
    "located_in",
    "Connecticut"
   ],
   [
    "West River",
    "country",
    "Canada"
   ],
   [
    "West River",
    "located_in",
    "Nova Scotia"
   ],
   [
    "West River",
    "country",
    "Australia"
   ],
   [
    "West River",
    "located_in",
    "Shire of Ravensthorpe"
   ],
   [
    "West River",
    "located_in",
    "Western Australia"
   ],
   [
    "West River",
    "located_in",
    "New Brunswick"
   ]
  ]
 },
 {
  "entity": "Adamovka, Adamovsky District, Orenburg Oblast",
  "kind": "human settlement",
  "facts": [
   [
    "Adamovka, Adamovsky District, Orenburg Oblast",
    "country",
    "Russia"
   ],
   [
    "Adamovka, Adamovsky District, Orenburg Oblast",
    "located_in",
    "Adamovsky District"
   ]
  ]
 },
 {
  "entity": "Badamestan-e Bala",
  "kind": "human settlement",
  "facts": [
   [
    "Badamestan-e Bala",
    "located_in",
    "Central District"
   ],
   [
    "Badamestan-e Bala",
    "located_in",
    "Madvarat Rural District"
   ],
   [
    "Badamestan-e Bala",
    "country",
    "Iran"
   ]
  ]
 },
 {
  "entity": "Bqerzla",
  "kind": "human settlement",
  "facts": [
   [
    "Bqerzla",
    "country",
    "Lebanon"
   ],
   [
    "Bqerzla",
    "located_in",
    "Akkar District"
   ]
  ]
 },
 {
  "entity": "Eslamabad, Chahar Gonbad",
  "kind": "human settlement",
  "facts": [
   [
    "Eslamabad, Chahar Gonbad",
    "country",
    "Iran"
   ],
   [
    "Eslamabad, Chahar Gonbad",
    "located_in",
    "Chahar Gonbad Rural District"
   ]
  ]
 },
 {
  "entity": "HaZor'im",
  "kind": "human settlement",
  "facts": [
   [
    "HaZor'im",
    "country",
    "Israel"
   ],
   [
    "HaZor'im",
    "located_in",
    "Lower Galilee Regional Council"
   ]
  ]
 },
 {
  "entity": "Kalameshwar",
  "kind": "human settlement",
  "facts": [
   [
    "Kalameshwar",
    "country",
    "India"
   ],
   [
    "Kalameshwar",
    "located_in",
    "Nagpur district"
   ],
   [
    "Kalameshwar",
    "located_in",
    "Maharashtra"
   ]
  ]
 },
 {
  "entity": "Koranit",
  "kind": "human settlement",
  "facts": [
   [
    "Koranit",
    "country",
    "Israel"
   ],
   [
    "Koranit",
    "located_in",
    "Misgav Regional Council"
   ]
  ]
 },
 {
  "entity": "Moloundou",
  "kind": "human settlement",
  "facts": [
   [
    "Moloundou",
    "country",
    "Republic of the Congo"
   ],
   [
    "Moloundou",
    "country",
    "Cameroon"
   ],
   [
    "Moloundou",
    "country",
    "Kamerun"
   ],
   [
    "Moloundou",
    "located_in",
    "Boumba-et-Ngoko"
   ]
  ]
 },
 {
  "entity": "Deposition",
  "kind": "literary work",
  "facts": [
   [
    "Deposition",
    "alias",
    "A flashy con artist, often homeless, who lives by his wits"
   ],
   [
    "Deposition",
    "located_in",
    "Galleria nazionale di Parma"
   ],
   [
    "Deposition",
    "creator",
    "Bartolomeo Schedoni"
   ],
   [
    "Deposition",
    "genre",
    "religious art"
   ],
   [
    "Deposition",
    "religion",
    "Christianity"
   ],
   [
    "Deposition",
    "located_in",
    "Auckland Art Gallery"
   ],
   [
    "Deposition",
    "creator",
    "Jeffrey Harris"
   ],
   [
    "Deposition",
    "creator",
    "Sebastiano Conca"
   ],
   [
    "Deposition",
    "located_in",
    "Pinacoteca Vaticana"
   ],
   [
    "Deposition",
    "creator",
    "Anthony van Dyck"
   ],
   [
    "Deposition",
    "made_of",
    "oil paint"
   ],
   [
    "Deposition",
    "made_of",
    "panel"
   ]
  ]
 },
 {
  "entity": "Scarlet",
  "kind": "literary work",
  "facts": [
   [
    "Scarlet",
    "defined_as",
    "thyreostatic"
   ],
   [
    "Scarlet",
    "genre",
    "pop rock"
   ],
   [
    "Scarlet",
    "country",
    "United Kingdom"
   ],
   [
    "Scarlet",
    "part_of",
    "October"
   ],
   [
    "Scarlet",
    "country",
    "Ireland"
   ],
   [
    "Scarlet",
    "author",
    "Stephen R. Lawhead"
   ],
   [
    "Scarlet",
    "country",
    "United States"
   ],
   [
    "Scarlet",
    "located_in",
    "Northwest Township"
   ],
   [
    "Scarlet",
    "country",
    "Japan"
   ],
   [
    "Scarlet",
    "genre",
    "drama television series"
   ],
   [
    "Scarlet",
    "genre",
    "Japanese television drama"
   ],
   [
    "Scarlet",
    "genre",
    "yuri"
   ]
  ]
 },
 {
  "entity": "Heat of the Moment",
  "kind": "literary work",
  "facts": [
   [
    "Heat of the Moment",
    "country",
    "United States"
   ],
   [
    "Heat of the Moment",
    "author",
    "Lori Handeland"
   ],
   [
    "Heat of the Moment",
    "genre",
    "rock music"
   ],
   [
    "Heat of the Moment",
    "genre",
    "progressive rock"
   ],
   [
    "Heat of the Moment",
    "has_property",
    "debut single"
   ],
   [
    "Heat of the Moment",
    "genre",
    "rhythm and blues"
   ]
  ]
 },
 {
  "entity": "Arthur the King",
  "kind": "literary work",
  "facts": [
   [
    "Arthur the King",
    "country",
    "United States"
   ],
   [
    "Arthur the King",
    "country",
    "Canada"
   ],
   [
    "Arthur the King",
    "genre",
    "adventure film"
   ],
   [
    "Arthur the King",
    "genre",
    "drama film"
   ],
   [
    "Arthur the King",
    "has_property",
    "film based on book"
   ],
   [
    "Arthur the King",
    "author",
    "Allan Massie"
   ]
  ]
 },
 {
  "entity": "Dark Side of the Morgue",
  "kind": "literary work",
  "facts": [
   [
    "Dark Side of the Morgue",
    "author",
    "Raymond Benson"
   ],
   [
    "Dark Side of the Morgue",
    "genre",
    "thriller"
   ],
   [
    "Dark Side of the Morgue",
    "genre",
    "mystery fiction"
   ],
   [
    "Dark Side of the Morgue",
    "country",
    "United States"
   ]
  ]
 },
 {
  "entity": "Frederick Douglass",
  "kind": "literary work",
  "facts": [
   [
    "Frederick Douglass",
    "occupation",
    "journalist"
   ],
   [
    "Frederick Douglass",
    "occupation",
    "diplomat"
   ],
   [
    "Frederick Douglass",
    "occupation",
    "writer"
   ],
   [
    "Frederick Douglass",
    "occupation",
    "editor"
   ],
   [
    "Frederick Douglass",
    "occupation",
    "suffragist"
   ],
   [
    "Frederick Douglass",
    "occupation",
    "abolitionist"
   ],
   [
    "Frederick Douglass",
    "occupation",
    "orator"
   ],
   [
    "Frederick Douglass",
    "occupation",
    "caulker"
   ],
   [
    "Frederick Douglass",
    "occupation",
    "politician"
   ],
   [
    "Frederick Douglass",
    "occupation",
    "autobiographer"
   ],
   [
    "Frederick Douglass",
    "occupation",
    "film editor"
   ],
   [
    "Frederick Douglass",
    "occupation",
    "slave"
   ]
  ]
 },
 {
  "entity": "Iron Sunrise",
  "kind": "literary work",
  "facts": [
   [
    "Iron Sunrise",
    "author",
    "Charles Stross"
   ],
   [
    "Iron Sunrise",
    "genre",
    "libertarian science fiction"
   ],
   [
    "Iron Sunrise",
    "genre",
    "postcyberpunk"
   ],
   [
    "Iron Sunrise",
    "genre",
    "hard science fiction"
   ],
   [
    "Iron Sunrise",
    "genre",
    "science fiction"
   ],
   [
    "Iron Sunrise",
    "country",
    "United Kingdom"
   ]
  ]
 },
 {
  "entity": "Pay Any Price: Greed, Power, and Endless War",
  "kind": "literary work",
  "facts": [
   [
    "Pay Any Price: Greed, Power, and Endless War",
    "author",
    "James Risen"
   ],
   [
    "Pay Any Price: Greed, Power, and Endless War",
    "country",
    "United States"
   ]
  ]
 },
 {
  "entity": "Skylark DuQuesne",
  "kind": "literary work",
  "facts": [
   [
    "Skylark DuQuesne",
    "genre",
    "science fiction"
   ],
   [
    "Skylark DuQuesne",
    "author",
    "Edward Elmer Smith"
   ],
   [
    "Skylark DuQuesne",
    "country",
    "United States"
   ]
  ]
 },
 {
  "entity": "The American Experiment",
  "kind": "literary work",
  "facts": [
   [
    "The American Experiment",
    "author",
    "Steven M. Gillon"
   ],
   [
    "The American Experiment",
    "country",
    "United States"
   ]
  ]
 },
 {
  "entity": "The King's Speech",
  "kind": "literary work",
  "facts": [
   [
    "The King's Speech",
    "director",
    "Tom Hooper"
   ],
   [
    "The King's Speech",
    "country",
    "United Kingdom"
   ],
   [
    "The King's Speech",
    "genre",
    "biographical film"
   ],
   [
    "The King's Speech",
    "genre",
    "drama film"
   ],
   [
    "The King's Speech",
    "genre",
    "historical film"
   ],
   [
    "The King's Speech",
    "author",
    "David Seidler"
   ]
  ]
 },
 {
  "entity": "The Plague Court Murders",
  "kind": "literary work",
  "facts": [
   [
    "The Plague Court Murders",
    "author",
    "John Dickson Carr"
   ],
   [
    "The Plague Court Murders",
    "genre",
    "crime fiction"
   ],
   [
    "The Plague Court Murders",
    "country",
    "United Kingdom"
   ]
  ]
 },
 {
  "entity": "Braut",
  "kind": "painting",
  "facts": [
   [
    "Braut",
    "country",
    "Norway"
   ],
   [
    "Braut",
    "located_in",
    "Klepp Municipality"
   ],
   [
    "Braut",
    "located_in",
    "Munich Central Collecting Point"
   ],
   [
    "Braut",
    "country",
    "Iceland"
   ]
  ]
 },
 {
  "entity": "Tranquility",
  "kind": "painting",
  "facts": [
   [
    "Tranquility",
    "defined_as",
    "An unincorporated community in Adams, Ohio, United States"
   ],
   [
    "Tranquility",
    "defined_as",
    "Ellipsis of Sea of Tranquility"
   ],
   [
    "Tranquility",
    "defined_as",
    "A neighbourhood of Queens, New York City"
   ],
   [
    "Tranquility",
    "defined_as",
    "A neighbourhood of Staten Island, New York City"
   ],
   [
    "Tranquility",
    "genre",
    "music video game"
   ],
   [
    "Tranquility",
    "country",
    "United States"
   ],
   [
    "Tranquility",
    "country",
    "United Kingdom"
   ],
   [
    "Tranquility",
    "located_in",
    "Penryn"
   ],
   [
    "Tranquility",
    "located_in",
    "Hungarian National Gallery"
   ],
   [
    "Tranquility",
    "located_in",
    "Mount Vernon East station"
   ],
   [
    "Tranquility",
    "creator",
    "Marjorie Blackwell"
   ],
   [
    "Tranquility",
    "genre",
    "public art"
   ]
  ]
 },
 {
  "entity": "Iris Murdoch",
  "kind": "painting",
  "facts": [
   [
    "Iris Murdoch",
    "located_in",
    "National Portrait Gallery"
   ],
   [
    "Iris Murdoch",
    "genre",
    "portrait"
   ],
   [
    "Iris Murdoch",
    "creator",
    "Tom Phillips"
   ],
   [
    "Iris Murdoch",
    "occupation",
    "poet"
   ],
   [
    "Iris Murdoch",
    "occupation",
    "philosopher"
   ],
   [
    "Iris Murdoch",
    "occupation",
    "novelist"
   ],
   [
    "Iris Murdoch",
    "occupation",
    "prose writer"
   ],
   [
    "Iris Murdoch",
    "occupation",
    "biographer"
   ],
   [
    "Iris Murdoch",
    "occupation",
    "professor"
   ],
   [
    "Iris Murdoch",
    "occupation",
    "writer"
   ],
   [
    "Iris Murdoch",
    "employer",
    "University of Oxford"
   ],
   [
    "Iris Murdoch",
    "employer",
    "St Anne's College"
   ]
  ]
 },
 {
  "entity": "Thomas Woolner",
  "kind": "painting",
  "facts": [
   [
    "Thomas Woolner",
    "occupation",
    "sculptor"
   ],
   [
    "Thomas Woolner",
    "occupation",
    "poet"
   ],
   [
    "Thomas Woolner",
    "occupation",
    "writer"
   ],
   [
    "Thomas Woolner",
    "creator",
    "Alphonse Legros"
   ],
   [
    "Thomas Woolner",
    "made_of",
    "oil paint"
   ],
   [
    "Thomas Woolner",
    "made_of",
    "canvas"
   ]
  ]
 },
 {
  "entity": "Telemachus and Mentor",
  "kind": "painting",
  "facts": [
   [
    "Telemachus and Mentor",
    "located_in",
    "Rijksmuseum"
   ],
   [
    "Telemachus and Mentor",
    "creator",
    "Giovanni Battista Tiepolo"
   ],
   [
    "Telemachus and Mentor",
    "made_of",
    "canvas"
   ],
   [
    "Telemachus and Mentor",
    "made_of",
    "oil paint"
   ],
   [
    "Telemachus and Mentor",
    "country",
    "Netherlands"
   ],
   [
    "Telemachus and Mentor",
    "located_in",
    "Yale Center for British Art"
   ],
   [
    "Telemachus and Mentor",
    "creator",
    "John Doyle"
   ],
   [
    "Telemachus and Mentor",
    "made_of",
    "ink"
   ],
   [
    "Telemachus and Mentor",
    "made_of",
    "lithograph print"
   ],
   [
    "Telemachus and Mentor",
    "made_of",
    "wove paper"
   ]
  ]
 },
 {
  "entity": "Shobdon Folly: Romanesque Fragments",
  "kind": "painting",
  "facts": [
   [
    "Shobdon Folly: Romanesque Fragments",
    "located_in",
    "Museum of Fine Arts Boston"
   ],
   [
    "Shobdon Folly: Romanesque Fragments",
    "creator",
    "John Piper"
   ],
   [
    "Shobdon Folly: Romanesque Fragments",
    "made_of",
    "oil paint"
   ],
   [
    "Shobdon Folly: Romanesque Fragments",
    "made_of",
    "canvas"
   ]
  ]
 },
 {
  "entity": "The Cloth Hall, Ypres",
  "kind": "painting",
  "facts": [
   [
    "The Cloth Hall, Ypres",
    "located_in",
    "Auckland Art Gallery"
   ],
   [
    "The Cloth Hall, Ypres",
    "made_of",
    "oil paint"
   ],
   [
    "The Cloth Hall, Ypres",
    "made_of",
    "canvas"
   ],
   [
    "The Cloth Hall, Ypres",
    "creator",
    "Robert Johnson"
   ],
   [
    "The Cloth Hall, Ypres",
    "creator",
    "James Kerr-Lawson"
   ],
   [
    "The Cloth Hall, Ypres",
    "located_in",
    "Chamber of the Senate of Canada"
   ],
   [
    "The Cloth Hall, Ypres",
    "located_in",
    "Cartwright Hall Art Gallery"
   ],
   [
    "The Cloth Hall, Ypres",
    "creator",
    "William Rothenstein"
   ],
   [
    "The Cloth Hall, Ypres",
    "creator",
    "David Milne"
   ],
   [
    "The Cloth Hall, Ypres",
    "made_of",
    "watercolor pencil"
   ],
   [
    "The Cloth Hall, Ypres",
    "made_of",
    "graphite pencil"
   ],
   [
    "The Cloth Hall, Ypres",
    "made_of",
    "wove paper"
   ]
  ]
 },
 {
  "entity": "My Portrait",
  "kind": "painting",
  "facts": [
   [
    "My Portrait",
    "located_in",
    "National Gallery of Canada"
   ],
   [
    "My Portrait",
    "creator",
    "Ozias Leduc"
   ]
  ]
 },
 {
  "entity": "Kiowa Family; Kiowa Mother & Children",
  "kind": "painting",
  "facts": [
   [
    "Kiowa Family; Kiowa Mother & Children",
    "located_in",
    "Gilcrease Museum"
   ],
   [
    "Kiowa Family; Kiowa Mother & Children",
    "creator",
    "Lois Smoky"
   ]
  ]
 },
 {
  "entity": "Blind Gustaf Fridhem",
  "kind": "painting",
  "facts": [
   [
    "Blind Gustaf Fridhem",
    "located_in",
    "Nationalmuseum"
   ],
   [
    "Blind Gustaf Fridhem",
    "creator",
    "Berndt Lindholm"
   ],
   [
    "Blind Gustaf Fridhem",
    "made_of",
    "oil paint"
   ],
   [
    "Blind Gustaf Fridhem",
    "made_of",
    "canvas"
   ]
  ]
 },
 {
  "entity": "Italian family scene",
  "kind": "painting",
  "facts": [
   [
    "Italian family scene",
    "genre",
    "genre art"
   ],
   [
    "Italian family scene",
    "creator",
    "Hortense Haudebourt-Lescot"
   ],
   [
    "Italian family scene",
    "made_of",
    "watercolor paint"
   ],
   [
    "Italian family scene",
    "country",
    "France"
   ]
  ]
 },
 {
  "entity": "The Launch of HMS 'Indomitable', Fairfield",
  "kind": "painting",
  "facts": [
   [
    "The Launch of HMS 'Indomitable', Fairfield",
    "located_in",
    "Glasgow Museums Resource Centre"
   ],
   [
    "The Launch of HMS 'Indomitable', Fairfield",
    "creator",
    "Charles William Wyllie"
   ],
   [
    "The Launch of HMS 'Indomitable', Fairfield",
    "made_of",
    "oil paint"
   ],
   [
    "The Launch of HMS 'Indomitable', Fairfield",
    "made_of",
    "canvas"
   ]
  ]
 },
 {
  "entity": "5",
  "kind": "video game",
  "facts": [
   [
    "5",
    "antonym",
    "3"
   ],
   [
    "5",
    "alias",
    "five"
   ],
   [
    "5",
    "defined_as",
    "Initialism of Music Elective Programme"
   ],
   [
    "5",
    "has_property",
    "five"
   ],
   [
    "5",
    "genre",
    "pop music"
   ],
   [
    "5",
    "creator",
    "Dan Flavin"
   ],
   [
    "5",
    "country",
    "United States"
   ],
   [
    "5",
    "genre",
    "soul"
   ],
   [
    "5",
    "part_of",
    "Lenny Kravitz' albums in chronological order"
   ],
   [
    "5",
    "genre",
    "visual kei"
   ],
   [
    "5",
    "genre",
    "chanson"
   ],
   [
    "5",
    "country",
    "Germany"
   ]
  ]
 },
 {
  "entity": "Traveler",
  "kind": "video game",
  "facts": [
   [
    "Traveler",
    "part_of",
    "Trey Anastasio's albums in chronological order"
   ],
   [
    "Traveler",
    "genre",
    "ambient music"
   ],
   [
    "Traveler",
    "part_of",
    "Steve Roach's albums in chronological order"
   ],
   [
    "Traveler",
    "genre",
    "J-pop"
   ],
   [
    "Traveler",
    "genre",
    "pop rock"
   ],
   [
    "Traveler",
    "part_of",
    "Hitomi's albums in chronological order"
   ],
   [
    "Traveler",
    "genre",
    "acoustic music"
   ],
   [
    "Traveler",
    "genre",
    "ballad in music"
   ],
   [
    "Traveler",
    "country",
    "Nigeria"
   ],
   [
    "Traveler",
    "author",
    "Helon Habila"
   ],
   [
    "Traveler",
    "genre",
    "adventure video game"
   ],
   [
    "Traveler",
    "genre",
    "role-playing video game"
   ]
  ]
 },
 {
  "entity": "3-D Monster Chase",
  "kind": "video game",
  "facts": [
   [
    "3-D Monster Chase",
    "genre",
    "maze video game"
   ],
   [
    "3-D Monster Chase",
    "country",
    "United Kingdom"
   ]
  ]
 },
 {
  "entity": "Blackguards 2",
  "kind": "video game",
  "facts": [
   [
    "Blackguards 2",
    "genre",
    "turn-based tactics"
   ],
   [
    "Blackguards 2",
    "country",
    "Germany"
   ],
   [
    "Blackguards 2",
    "has_property",
    "indie game"
   ]
  ]
 },
 {
  "entity": "Danny Phantom: The Ultimate Enemy",
  "kind": "video game",
  "facts": [
   [
    "Danny Phantom: The Ultimate Enemy",
    "genre",
    "side-scrolling video game"
   ],
   [
    "Danny Phantom: The Ultimate Enemy",
    "country",
    "Japan"
   ]
  ]
 },
 {
  "entity": "I Spy Spooky Mansion",
  "kind": "video game",
  "facts": [
   [
    "I Spy Spooky Mansion",
    "genre",
    "puzzle video game"
   ],
   [
    "I Spy Spooky Mansion",
    "country",
    "United States"
   ]
  ]
 },
 {
  "entity": "Manga Fighter",
  "kind": "video game",
  "facts": [
   [
    "Manga Fighter",
    "genre",
    "third-person shooter"
   ],
   [
    "Manga Fighter",
    "country",
    "Japan"
   ]
  ]
 },
 {
  "entity": "OhShape",
  "kind": "video game",
  "facts": [
   [
    "OhShape",
    "has_property",
    "indie game"
   ],
   [
    "OhShape",
    "genre",
    "action game"
   ],
   [
    "OhShape",
    "genre",
    "simulation video game"
   ],
   [
    "OhShape",
    "genre",
    "sports video game"
   ]
  ]
 },
 {
  "entity": "RimWorld",
  "kind": "video game",
  "facts": [
   [
    "RimWorld",
    "genre",
    "construction and management simulation"
   ],
   [
    "RimWorld",
    "genre",
    "hard science fiction"
   ],
   [
    "RimWorld",
    "genre",
    "science fiction video game"
   ],
   [
    "RimWorld",
    "country",
    "Canada"
   ],
   [
    "RimWorld",
    "has_property",
    "indie game"
   ]
  ]
 },
 {
  "entity": "The Secret of Monkey Island",
  "kind": "video game",
  "facts": [
   [
    "The Secret of Monkey Island",
    "has_property",
    "fan game"
   ],
   [
    "The Secret of Monkey Island",
    "genre",
    "adventure video game"
   ],
   [
    "The Secret of Monkey Island",
    "country",
    "United States"
   ],
   [
    "The Secret of Monkey Island",
    "director",
    "Ron Gilbert"
   ]
  ]
 },
 {
  "entity": "Campaign",
  "kind": "video game",
  "facts": [
   [
    "Campaign",
    "country",
    "United States"
   ],
   [
    "Campaign",
    "located_in",
    "Warren County"
   ],
   [
    "Campaign",
    "part_of",
    "Ty Dolla Sign's albums in chronological order"
   ],
   [
    "Campaign",
    "country",
    "Iran"
   ],
   [
    "Campaign",
    "director",
    "shahram asadzadeh"
   ],
   [
    "Campaign",
    "country",
    "United Kingdom"
   ],
   [
    "Campaign",
    "director",
    "Kazuhiro Soda"
   ],
   [
    "Campaign",
    "country",
    "Japan"
   ],
   [
    "Campaign",
    "genre",
    "documentary film"
   ],
   [
    "Campaign",
    "genre",
    "strategy video game"
   ]
  ]
 },
 {
  "entity": "Abu Simbel Profanation",
  "kind": "video game",
  "facts": [
   [
    "Abu Simbel Profanation",
    "genre",
    "platformer"
   ],
   [
    "Abu Simbel Profanation",
    "part_of",
    "Dinamic Hits Collection"
   ],
   [
    "Abu Simbel Profanation",
    "country",
    "Spain"
   ]
  ]
 },
 {
  "entity": "Jordan",
  "kind": "weather station",
  "facts": [
   [
    "Jordan",
    "defined_as",
    "A placename:"
   ],
   [
    "Jordan",
    "defined_as",
    "A number of places in the United States:"
   ],
   [
    "Jordan",
    "defined_as",
    "An unincorporated community in Boone County, Iowa"
   ],
   [
    "Jordan",
    "defined_as",
    "An unincorporated community in Fulton County, Kentucky"
   ],
   [
    "Jordan",
    "defined_as",
    "A city in Scott County, Minnesota"
   ],
   [
    "Jordan",
    "defined_as",
    "A neighbourhood of Minneapolis, Minnesota"
   ],
   [
    "Jordan",
    "defined_as",
    "An unincorporated community in Hickory County, Missouri"
   ],
   [
    "Jordan",
    "defined_as",
    "A small town, the county seat of Garfield County, Montana"
   ],
   [
    "Jordan",
    "defined_as",
    "A village in Onondaga County, New York"
   ],
   [
    "Jordan",
    "defined_as",
    "An unincorporated community in Linn County, Oregon"
   ],
   [
    "Jordan",
    "defined_as",
    "A town in Green County, Wisconsin"
   ],
   [
    "Jordan",
    "defined_as",
    "An area of Yau Tsim Mong district, Kowloon, Hong Kong"
   ]
  ]
 },
 {
  "entity": "Ida",
  "kind": "weather station",
  "facts": [
   [
    "Ida",
    "defined_as",
    "A female given name from the Germanic languages"
   ],
   [
    "Ida",
    "defined_as",
    "A surname"
   ],
   [
    "Ida",
    "defined_as",
    "A river in eastern Slovakia"
   ],
   [
    "Ida",
    "defined_as",
    "A female given name from Sanskrit used in India"
   ],
   [
    "Ida",
    "defined_as",
    "A long, narrow fishing boat used in shallow waters"
   ],
   [
    "Ida",
    "defined_as",
    "Clipping of sharp-shinned hawk"
   ],
   [
    "Ida",
    "defined_as",
    "Clipping of sharp-tailed sandpiper"
   ],
   [
    "Ida",
    "defined_as",
    "sharp"
   ],
   [
    "Ida",
    "occupation",
    "sovereign"
   ],
   [
    "Ida",
    "country",
    "United States"
   ],
   [
    "Ida",
    "located_in",
    "Caddo Parish"
   ],
   [
    "Ida",
    "occupation",
    "Christian nun"
   ]
  ]
 },
 {
  "entity": "Dinsmore",
  "kind": "weather station",
  "facts": [
   [
    "Dinsmore",
    "defined_as",
    "A surname"
   ],
   [
    "Dinsmore",
    "defined_as",
    "Any of a number of towns in English-speaking countries"
   ],
   [
    "Dinsmore",
    "defined_as",
    "A number of places in the United States:"
   ],
   [
    "Dinsmore",
    "country",
    "Canada"
   ],
   [
    "Dinsmore",
    "located_in",
    "Saskatchewan"
   ],
   [
    "Dinsmore",
    "country",
    "United States"
   ],
   [
    "Dinsmore",
    "located_in",
    "Humboldt County"
   ]
  ]
 },
 {
  "entity": "Forestville",
  "kind": "weather station",
  "facts": [
   [
    "Forestville",
    "defined_as",
    "A town and municipality in Santander department, Colombia"
   ],
   [
    "Forestville",
    "country",
    "Canada"
   ],
   [
    "Forestville",
    "country",
    "United States"
   ],
   [
    "Forestville",
    "located_in",
    "Door County"
   ],
   [
    "Forestville",
    "located_in",
    "Forestville Township"
   ],
   [
    "Forestville",
    "located_in",
    "Norfolk County"
   ],
   [
    "Forestville",
    "located_in",
    "Chautauqua County"
   ],
   [
    "Forestville",
    "located_in",
    "Prince George's County"
   ],
   [
    "Forestville",
    "located_in",
    "Quebec"
   ],
   [
    "Forestville",
    "located_in",
    "Iowa"
   ],
   [
    "Forestville",
    "located_in",
    "Hamilton County"
   ],
   [
    "Forestville",
    "country",
    "Australia"
   ]
  ]
 },
 {
  "entity": "Bow Island",
  "kind": "weather station",
  "facts": [
   [
    "Bow Island",
    "defined_as",
    "plural of computer science"
   ],
   [
    "Bow Island",
    "country",
    "Canada"
   ],
   [
    "Bow Island",
    "located_in",
    "Alberta"
   ],
   [
    "Bow Island",
    "located_in",
    "Manitoba"
   ],
   [
    "Bow Island",
    "country",
    "United States"
   ],
   [
    "Bow Island",
    "located_in",
    "Chippewa County"
   ]
  ]
 },
 {
  "entity": "Harrington Harbour",
  "kind": "weather station",
  "facts": [
   [
    "Harrington Harbour",
    "country",
    "Canada"
   ],
   [
    "Harrington Harbour",
    "located_in",
    "Quebec"
   ]
  ]
 },
 {
  "entity": "MIVA",
  "kind": "weather station",
  "facts": [
   [
    "MIVA",
    "country",
    "Austria"
   ],
   [
    "MIVA",
    "country",
    "Australia"
   ],
   [
    "MIVA",
    "located_in",
    "Queensland"
   ]
  ]
 },
 {
  "entity": "Sharpe Lake",
  "kind": "weather station",
  "facts": [
   [
    "Sharpe Lake",
    "country",
    "Canada"
   ],
   [
    "Sharpe Lake",
    "located_in",
    "British Columbia"
   ],
   [
    "Sharpe Lake",
    "located_in",
    "Manitoba"
   ],
   [
    "Sharpe Lake",
    "located_in",
    "Ontario"
   ],
   [
    "Sharpe Lake",
    "located_in",
    "Algoma District"
   ],
   [
    "Sharpe Lake",
    "located_in",
    "Saskatchewan"
   ]
  ]
 },
 {
  "entity": "St Nazaire",
  "kind": "weather station",
  "facts": [
   [
    "St Nazaire",
    "country",
    "Canada"
   ],
   [
    "St Nazaire",
    "located_in",
    "Quebec"
   ],
   [
    "St Nazaire",
    "country",
    "France"
   ],
   [
    "St Nazaire",
    "located_in",
    "Mulhouse"
   ]
  ]
 },
 {
  "entity": "Cypress Bowl Grandstand",
  "kind": "weather station",
  "facts": [
   [
    "Cypress Bowl Grandstand",
    "country",
    "Canada"
   ],
   [
    "Cypress Bowl Grandstand",
    "located_in",
    "British Columbia"
   ]
  ]
 },
 {
  "entity": "Beaufort-sur-Gervanne weather station",
  "kind": "weather station",
  "facts": [
   [
    "Beaufort-sur-Gervanne weather station",
    "country",
    "France"
   ],
   [
    "Beaufort-sur-Gervanne weather station",
    "located_in",
    "Beaufort-sur-Gervanne"
   ]
  ]
 },
 {
  "entity": "MIROOBIL",
  "kind": "weather station",
  "facts": [
   [
    "MIROOBIL",
    "country",
    "Australia"
   ],
   [
    "MIROOBIL",
    "located_in",
    "New South Wales"
   ]
  ]
 }
]

PREVALENCES: dict[str, dict[str, float]] = {
 "painting": {
  "country": 0.127024,
  "creator": 0.784552,
  "genre": 0.390021,
  "is_a": 1.0,
  "located_in": 0.828544,
  "made_of": 0.734727,
  "occupation": 0.021147,
  "part_of": 0.029614,
  "religion": 0.03022
 },
 "literary work": {
  "author": 0.829045,
  "country": 0.341853,
  "creator": 0.044485,
  "defined_as": 0.020358,
  "director": 0.088931,
  "genre": 0.359622,
  "has_a": 0.026829,
  "has_property": 0.040681,
  "is_a": 1.0,
  "located_in": 0.061614,
  "made_of": 0.029628,
  "part_of": 0.064177
 },
 "human settlement": {
  "country": 0.999017,
  "defined_as": 0.047761,
  "is_a": 1.0,
  "located_in": 0.957576,
  "part_of": 0.035537
 },
 "hill": {
  "country": 0.995196,
  "is_a": 1.0,
  "located_in": 0.857263
 },
 "weather station": {
  "country": 0.99837,
  "defined_as": 0.054405,
  "is_a": 1.0,
  "located_in": 0.994071,
  "part_of": 0.045459
 },
 "archaeological site": {
  "country": 0.934496,
  "has_a": 0.038047,
  "is_a": 1.0,
  "located_in": 0.844684,
  "part_of": 0.277209
 },
 "video game": {
  "author": 0.037636,
  "country": 0.27027,
  "creator": 0.029713,
  "director": 0.048287,
  "genre": 0.818871,
  "has_property": 0.322645,
  "is_a": 1.0,
  "located_in": 0.042729,
  "part_of": 0.03327
 },
 "encyclopedia article": {
  "author": 0.234481,
  "country": 0.025856,
  "is_a": 1.0,
  "part_of": 0.235905
 }
}


def evaluate() -> dict[str, float]:
    """Predict each frozen entity's kind from its behaviour. Calls the substrate directly."""
    from packages.substrate import behaviour_of, decisive_kind

    right = wrong = abstained = 0
    for row in CORPUS:
        facts = [tuple(f) for f in row["facts"]]
        got, _score, _why = decisive_kind(behaviour_of(row["entity"], facts), PREVALENCES)
        if got is None:
            abstained += 1
        elif got == row["kind"]:
            right += 1
        else:
            wrong += 1

    n = len(CORPUS)
    placed = right + wrong
    return {
        "accuracy_on_placed": round(right / placed, 6) if placed else 0.0,
        "coverage": round(placed / n, 6) if n else 0.0,
        "abstention_rate": round(abstained / n, 6) if n else 0.0,
        "correct": float(right),
        "wrong": float(wrong),
    }


def report() -> dict[str, Any]:
    return {"corpus": len(CORPUS), "kinds": len(PREVALENCES), **evaluate()}
