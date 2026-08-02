# -*- coding: utf-8 -*-
"""swe_eval — an HONEST SWE-bench harness for ATANOR.

Not a leaderboard chase. A stage-by-stage diagnostic of where ATANOR's real code organs
(code_reason.code_author / code_situation, self_repair) break on repo-scale GitHub-issue tasks. The
governing doctrine is fail-0: never emit a patch the engine cannot verify; abstaining on an instance
is honest, not a failure. A 0/N with a precise failure map is the intended result.
"""
