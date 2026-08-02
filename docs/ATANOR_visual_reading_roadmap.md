# ATANOR — Reading the screen like eyes (visual reading roadmap)

*Owner (2026-07-10): "브라우저가 텍스트만 따오는 게 아니라 화면을 정말로 읽게 — 사람이 눈으로 보듯
이미지·영상을 다 읽게. 스마트글래스처럼 실시간으로."* This is the honest plan, staged so each
layer ships something real and nothing is overclaimed.

## The architecture rule (already in the code)
The perception contract is **the vision runs client-side; only meaning leaves the page**
(`/api/perception/visual-ingest` takes detection *labels*, "frames never leave the page"). This is
both the smart-glasses model and the privacy guarantee: the eye is local, only what it *understood*
is sent. Everything below obeys it. And it obeys the No-LLM-for-facts rule: OCR/detection is
*perception* (reading what is there), which is learned-LANGUAGE, not fabricated facts — safe.

## Layer 0 — visual metadata  ✅ SHIPPED (extension v0.3)
The extension now reads the page's **visual layer** without any model: image `alt`/`title`,
`figcaption`, video titles/`aria-label`, and a media inventory (`이미지 N개, 영상 M개`). This rides
along with the body text into the same shielded pipeline. It's exactly what a screen reader gives a
blind user — the grounded identity of what's shown. Real, zero-dependency, live now.
*Limit:* it reads what the page *declares* about its media, not the pixels.

## Layer 1 — in-browser OCR (text inside images / screenshots)  → NEXT
Bundle **Tesseract.js** (WASM) in the extension. On each capture, OCR the on-screen images (and,
for canvas/video-heavy pages, a `chrome.tabs.captureVisibleTab` screenshot), extract the text, and
merge it into the ingest payload. This reads text the DOM does not expose — infographics, memes,
slides, screenshots, video thumbnails. Grounded (it's literally the text on screen). *One setup
step:* add the Tesseract assets to the extension bundle (MV3 CSP blocks remote script in content
scripts, so it must be bundled or run in an offscreen document).

## Layer 2 — in-browser object/scene detection  → THEN
Run **TensorFlow.js + COCO-SSD** (or a MobileNet classifier) client-side on the visible frame →
object/scene *labels* → POST to the existing `/api/perception/visual-ingest` (which already records
sightings on the episodic timeline and drives the possession/suggestion primitives). Now ATANOR
knows a page *shows a car, a chart, a person*, not just that an `<img>` exists.

## Layer 3 — real-time video & the smart-glasses stream  → TRACK
Sample `<video>` frames (and, on the glasses, the camera stream) at a bounded rate; run Layers 1–2
per keyframe; feed the perception stream so the timeline is a *life log*, not a frame log (the
per-label 60s cooldown already exists for exactly this). This is the same pipeline the
`/perception` page and the smart-glasses system use — the browser becomes one more eye into the
same visual-KG (`packages/perception/visual_kg.py`, `visual_memory.py`).

## Owner-supplied references (2026-07-10) — for when the perception layers are built
These inform Layers 1–3; none run in a browser-extension context as-is (research / multi-GB models),
so they are roadmap inputs, not ship-now:
- **Observer** (github.com/Roy3838/Observer) — a local screen-watching agent loop; closest to our
  "eyes on the screen" model and the Ato-orb activity overlay. Architecture is directly borrowable.
- **LocateAnything-3B** (huggingface nvidia) — open-vocabulary localization; a Layer-2 detector, but
  3B params ⇒ needs a GPU host, not the client. Would live behind a local /perception endpoint, and
  only its LABELS would ride the "frames never leave" contract.
- **Face recognition** (PMC8677765) — method reference for a *consented, local-only* face layer;
  gated by the same privacy contract (labels/embeddings local, never uploaded).
- **splat_analyzer** (github.com/nigelhartman/splat_analyzer) — 3D Gaussian-splat analysis; ties to
  the SPLATRA track, not the browser-read path.

## Honest scope
Layer 0 ships today and is real. Layers 1–3 are **model-bearing client-side capabilities** — each
is a concrete, bounded build (a named library, a known integration point), not research. The
sequence matters: OCR (most grounded) → detection → real-time. Full open-vocabulary scene
*description* is the frontier and stays clearly labeled as perception, never as fact.
