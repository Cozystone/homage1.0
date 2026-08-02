// ATANOR Surfer — OCR module (Layer 1 of "reading the screen like eyes").
// Reads TEXT INSIDE IMAGES that the DOM does not expose — infographics, memes, slides, chart
// labels, screenshots, video thumbnails. Runs Tesseract.js (WASM) fully IN-BROWSER, so pixels
// never leave the page; only the recognized text is merged into the ingest (same shield pipeline).
//
// ACTIVATION (one asset step — the code is complete, the binaries are a download):
//   1. Put these into extensions/atanor-surfer/vendor/ :
//        tesseract.min.js        (Tesseract.js UMD build)
//        tesseract-core.wasm.js  (core)
//        worker.min.js           (worker)
//        kor.traineddata.gz, eng.traineddata.gz   (language data)
//   2. In manifest.json add "vendor/*" to web_accessible_resources, and load vendor/tesseract.min.js
//      as the FIRST content script (so window.Tesseract exists before this file runs).
// Until then window.Tesseract is undefined and this module cleanly does nothing (no crash).

(function () {
  const MAX_IMAGES = 4;        // OCR is ~1-2s/image; cap it so browsing stays snappy
  const MIN_SIDE = 200;        // skip icons/thumbnails too small to hold readable text

  function candidateImages() {
    return Array.from(document.images || [])
      .filter((im) => im.naturalWidth >= MIN_SIDE && im.naturalHeight >= MIN_SIDE && im.src &&
        !im.src.startsWith("data:") /* huge inline data URLs are usually decorative */)
      .sort((a, b) => b.naturalWidth * b.naturalHeight - a.naturalWidth * a.naturalHeight)
      .slice(0, MAX_IMAGES);
  }

  // returns recognized text from on-screen images, or "" (also "" when Tesseract isn't bundled yet)
  window.atanorOCR = async function atanorOCR() {
    if (typeof window.Tesseract === "undefined") return "";
    const imgs = candidateImages();
    if (!imgs.length) return "";
    const base = chrome.runtime.getURL("vendor/");
    const out = [];
    for (const im of imgs) {
      try {
        const { data } = await window.Tesseract.recognize(im.src, "kor+eng", {
          workerPath: base + "worker.min.js",
          corePath: base,          // v5 picks tesseract-core-simd.wasm.js from this dir
          langPath: base,          // fetches kor.traineddata.gz / eng.traineddata.gz here
        });
        const text = (data && data.text ? data.text : "").replace(/\s+/g, " ").trim();
        if (text.length >= 8) out.push(text);
      } catch (_e) {
        /* one image failing must not abort the page */
      }
    }
    return out.length ? "[이미지 속 글자(OCR)] " + out.join(" · ") : "";
  };
})();
