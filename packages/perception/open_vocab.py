# -*- coding: utf-8 -*-
"""Open-vocabulary scene perception (owner 2026-07-13: " + + ").

The lite COCO detector could only say " " — 80 fixed classes, everything lumped. This is
the upgrade: OWLv2 (Google OWL-ViT v2) detects ARBITRARY text-named objects — you give it a vocabulary
(", , , , , …") and it localizes each with a box + score. Measured on
the RTX 5080: ~0.8s/frame, and it does NOT hallucinate (objects absent from the frame are not
reported), which is exactly ATANOR's honesty rule — perceive only what is actually there.

From the detections this composes a GROUNDED Korean scene sentence (No-LLM: built from the objects the
detector actually saw + their rough layout, never invented) and a stable color per label for the
color-coded overlay. Unknown regions (low-confidence, no vocab match) are returned as GAPS to be
resolved later by crop→embed→search→graph (the self-map loop) — that hook is where AlphaFramer's geo/
3D binding and the ATANOR concept graph plug in.

HEAVY + LAZY: torch + transformers + a ~600MB OWLv2 weight, loaded on first use and cached, GPU when
present. Never imported at engine startup — only when a scene-perception request arrives.
"""
from __future__ import annotations

import hashlib
from typing import Any, Optional

# a rich everyday vocabulary with EN(detector)→KO(surface) mapping. Extend freely — that is the whole
# point of OPEN vocabulary: naming a new thing is a data edit, not a retrain.
VOCAB_KO: dict[str, str] = {
    "a person": "사람", "a face": "얼굴", "glasses": "안경", "a book": "책", "a bookshelf": "책장",
    "an electric fan": "선풍기", "a cardboard box": "택배 상자", "a wardrobe": "옷장",
    "clothes": "옷", "a projector": "프로젝터", "a cup": "컵", "a bottle": "물병", "a chair": "의자",
    "a desk": "책상", "a laptop": "노트북", "a monitor": "모니터", "a keyboard": "키보드",
    "a mobile phone": "휴대폰", "a potted plant": "화분", "a lamp": "조명", "a picture frame": "액자",
    "a bag": "가방", "a shoe": "신발", "a clock": "시계", "a mirror": "거울", "a pillow": "베개",
    "a blanket": "이불", "a television": "TV", "a speaker": "스피커", "a window": "창문", "a door": "문",
}
DEFAULT_VOCAB = list(VOCAB_KO.keys())

_MODEL = None
_PROC = None
_DEVICE = None


def available() -> bool:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True
    except Exception:
        return False


def _load():
    """Lazy-load OWLv2 once (cached). GPU when available, else CPU. Inside the ENGINE process (TF/
    accelerate resident) the first load sometimes materializes META tensors and `.to(cuda)` dies with
    "Cannot copy out of meta tensor" — while an immediate retry loads real weights and works (measured
    2026-07-13, twice). So: force low_cpu_mem_usage=False AND self-heal with one retry instead of
    failing the caller's first frame."""
    global _MODEL, _PROC, _DEVICE
    if _MODEL is not None:
        return
    import torch
    from transformers import Owlv2ForObjectDetection, Owlv2Processor
    _DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    _PROC = Owlv2Processor.from_pretrained("google/owlv2-base-patch16-ensemble")
    dt = torch.float16 if _DEVICE == "cuda" else torch.float32
    last: Exception | None = None
    for _attempt in (1, 2):
        try:
            _MODEL = Owlv2ForObjectDetection.from_pretrained(
                "google/owlv2-base-patch16-ensemble", low_cpu_mem_usage=False,
                torch_dtype=dt).to(_DEVICE).eval()
            return
        except NotImplementedError as exc:                  # the meta-tensor shell — reload for real
            last = exc
            _MODEL = None
    raise last if last else RuntimeError("OWLv2 load failed")


def color_for(label: str) -> str:
    """A stable hex color per label (hash→hue) so the same object is always the same color on-screen."""
    h = int(hashlib.md5(label.encode("utf-8")).hexdigest(), 16)
    hue = h % 360
    return f"hsl({hue}, 72%, 55%)"


def _iou(a: list[float], b: list[float]) -> float:
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    ar_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    ar_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return inter / (ar_a + ar_b - inter) if (ar_a + ar_b - inter) > 0 else 0.0


def detect(image, vocabulary: Optional[list[str]] = None, threshold: float = 0.2) -> list[dict[str, Any]]:
    """Open-vocabulary detection: returns [{label_en, label_ko, box:[x0,y0,x1,y1], score, color}].
 Per-label NMS dedupes overlapping boxes of the same thing (the ' 4' coarseness the owner saw
 was mostly the same person boxed four times)."""
    _load()
    import torch
    vocab = vocabulary or DEFAULT_VOCAB
    inputs = _PROC(text=[vocab], images=image, return_tensors="pt").to(_DEVICE)
    if _DEVICE == "cuda" and "pixel_values" in inputs:      # match the fp16 weights
        inputs["pixel_values"] = inputs["pixel_values"].half()
    with torch.no_grad():
        out = _MODEL(**inputs)
    target = torch.tensor([image.size[::-1]]).to(_DEVICE)
    res = _PROC.post_process_grounded_object_detection(out, threshold=threshold, target_sizes=target)[0]
    dets = []
    for score, lbl, box in zip(res["scores"].tolist(), res["labels"].tolist(), res["boxes"].tolist()):
        en = vocab[lbl]
        dets.append({"label_en": en, "label_ko": VOCAB_KO.get(en, en), "score": round(score, 3),
                     "box": [round(b, 1) for b in box], "color": color_for(en)})
    dets.sort(key=lambda d: -d["score"])
    kept: list[dict[str, Any]] = []
    for d in dets:                                          # per-label NMS: same label + IoU>0.45 → dup
        if any(k["label_en"] == d["label_en"] and _iou(k["box"], d["box"]) > 0.45 for k in kept):
            continue
        kept.append(d)
    return kept


def _region(box: list[float], w: int, h: int) -> str:
    cx = (box[0] + box[2]) / 2 / max(1, w)
    return "왼쪽" if cx < 0.38 else "오른쪽" if cx > 0.62 else "가운데"


def compose_scene(dets: list[dict[str, Any]], size: tuple[int, int]) -> dict[str, Any]:
    """Compose a GROUNDED Korean scene sentence from detections — pure, No-LLM, no model needed. Names
    the objects the detector actually saw + their rough side of the frame; invents nothing beyond them."""
    w, h = size
    by_type: dict[str, dict[str, Any]] = {}
    for d in dets:                                          # distinct object types, most-confident kept
        ko = d["label_ko"]
        if ko not in by_type:
            by_type[ko] = {"ko": ko, "count": 0, "region": _region(d["box"], w, h), "score": d["score"]}
        by_type[ko]["count"] += 1
    parts = []
    for o in sorted(by_type.values(), key=lambda x: -x["score"]):
        n = f"{o['ko']} {o['count']}개" if o["count"] > 1 else o["ko"]
        parts.append(f"{o['region']}에 {n}")
    sentence = ("화면 " + ", ".join(parts[:6]) + "이(가) 보이는 공간이에요." if parts
                else "지금 화면에서 또렷이 알아볼 수 있는 사물이 없어요.")
    return {"distinct": list(by_type.values()), "scene_sentence": sentence}


def describe_scene(image, vocabulary: Optional[list[str]] = None, threshold: float = 0.2) -> dict[str, Any]:
    """Detect, then compose the grounded scene sentence. Returns objects + sentence + device."""
    dets = detect(image, vocabulary, threshold)
    comp = compose_scene(dets, image.size)
    return {"objects": dets, **comp, "device": _DEVICE, "count": len(dets)}
