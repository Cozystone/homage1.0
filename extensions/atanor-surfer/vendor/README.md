# OCR assets (present, but injection PAUSED — see note)

⚠️ **2026-07-10: `vendor/tesseract.min.js` was REMOVED from `content_scripts`.** Injecting the
Tesseract UMD bundle into every page tripped an MV3 error (its runtime uses eval/dynamic-Worker
patterns MV3 blocks in content scripts, and injecting a heavy WASM lib on every page is the wrong
pattern). The assets below are still bundled and correct; OCR just needs to run the RIGHT MV3 way —
in an **offscreen document** (`chrome.offscreen`), which loads Tesseract once, off the page, and
returns only text. That is a small dedicated follow-up. `content.js` already guards the call
(`typeof window.atanorOCR === "function"`), so with the injection removed OCR simply no-ops and the
extension loads cleanly.

Files here:
- `tesseract.min.js` — Tesseract.js v5 (exposes `window.Tesseract`)
- `worker.min.js` — worker
- `tesseract-core-simd.wasm.js` + `tesseract-core-simd.wasm` — SIMD WASM core
- `eng.traineddata.gz`, `kor.traineddata.gz` — English + Korean language data (tessdata 4.0.0)

The large binaries (`*.wasm`, `*.traineddata.gz`) are git-ignored (they are re-downloadable from the
CDN / tessdata) but MUST be present on disk for the extension to run. To refetch:
```
curl -sL -o tesseract.min.js            https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js
curl -sL -o worker.min.js               https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/worker.min.js
curl -sL -o tesseract-core-simd.wasm.js https://cdn.jsdelivr.net/npm/tesseract.js-core@5.1.1/tesseract-core-simd.wasm.js
curl -sL -o tesseract-core-simd.wasm    https://cdn.jsdelivr.net/npm/tesseract.js-core@5.1.1/tesseract-core-simd.wasm
curl -sL -o eng.traineddata.gz          https://tessdata.projectnaptha.com/4.0.0/eng.traineddata.gz
curl -sL -o kor.traineddata.gz          https://tessdata.projectnaptha.com/4.0.0/kor.traineddata.gz
```
