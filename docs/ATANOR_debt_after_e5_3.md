# Debt that unblocks the moment the E5-3 seal is spent

Two repairs are queued behind a live seal. Both are known, both are small, and both were deferred for
the same reason: `scripts/e5_b1_closeout.py` is a **B file** in the running E5-3 seal, and editing one
byte of a B file voids a measurement that is still in flight. Deferring them was the right call, and
forgetting them would not be — hence this file.

## 1. The fixed output path that already destroyed a record

`e5_b1_closeout.py` writes to a constant, `data/e5_transfer_seal/b1_closeout.json`. Running it for
E5-2 overwrote E5-1's record; running it for E5-3 overwrote E5-2's. Each number survived only because
it had also been copied into a prereg and a commit message.

**This is the same defect as the destructive default in `codebase_ingest.ingest_codebase`**, found and
fixed earlier the same day: an artifact path that ignores which run produced it. There the fix was to
derive every output path from the caller's arguments, and it is the same fix here.

Interim mitigation already in place: `data/e5_measurements/` is a **ledger room** holding all three
runs, and `rooms.place()` refuses a second write to the same name — verified. So the records are safe
now; the script is still wrong.

```
e5_1_b1_closeout.json   5,973 ->  6,768   +13.3%
e5_2_b1_arm.json        6,768 ->  7,127    +5.3%
e5_3_b1_arm.json        7,127 -> 12,299   +72.6%
```

Each baseline equals the previous run's result exactly, which is the evidence that the procedure is
reproducible — the property E5-1 lacked and E5-2 was rebuilt to provide.

## 2. The stale label on a reused script

`e5_b1_closeout.py` prints `"kind": "POST-HOC DIAGNOSTIC, not sealed E5 evidence"` into every result.
That was true when it was written for E5-1's closeout. It has since been promoted to **the sealed B1
measurement procedure** for E5-2 and E5-3, so the label now contradicts the seal that names it.

Not corrected in place for the same reason as above. Recorded in both preregs instead, so a later
reader does not take a result's own header as a verdict on itself.

## 3. The full `workspace` suture

`workspace` was tested today (7 behaviours, orphan list 15 → 14), but tests make a module *exercised*,
not *used*. The real suture is routing the closeout's output through a ledger room instead of a
constant — which is item 1. **The debt and the suture are the same edit**, which is the tidiest thing
about this list.

## Order

1. Score E5-3 and let the seal expire.
2. Make the closeout take its output path from the run. This clears items 1 and 3 together.
3. Fix the label. One line.
4. Re-run the reachability census afterwards, correctly this time — it went 55 → 15 → 3 → 0 today, and
   the honest reading is that the census taught nothing the behaviour checks had not already found.
