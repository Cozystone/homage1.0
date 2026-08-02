# -*- coding: utf-8 -*-
"""Realcity learning organ — pure, side-effect-free harvest transforms for the overhear loop.

See ``harvest.py``. Persistence deliberately lives OUTSIDE this package, in
``apps/api/app/routers/realcity_learning.py``, behind one monkeypatchable ``DATA_DIR`` — so this
package holds only the doctrine-critical text transforms (moral gate, anonymize, dialogue-act tag,
consensus-normalize, topic-extract) and can be unit-tested and reused without touching disk.
"""
