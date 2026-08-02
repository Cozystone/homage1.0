"use client";
// 실시간 지각 스트림 v0 (Phase 4-5) — 후면 카메라 + 온디바이스 객체감지.
// 원칙: 프레임 비저장. 감지는 전부 이 페이지 안(WASM CNN)에서 일어나고,
// 서버로 가는 것은 라벨 문자열뿐이다(127.0.0.1). 본 것은 에피소드 타임라인에
// 기록되고, 물병 시나리오 프리미티브가 근거 있는 제안만 돌려준다.
import { useEffect, useRef, useState } from "react";

const MP_VER = "0.10.14";
const MP_URL = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${MP_VER}`;
const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float16/1/efficientdet_lite0.tflite";
const POSE_MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task";
// FACE landmarker — 468 points + 52 expression blendshapes, WASM in-browser (light, private, no
// frame leaves). This is why the face wasn't caught: DeepFace(server, heavy) is for IDENTITY; a
// robust face DETECTOR + EXPRESSION + MOVEMENT belongs on-device (owner 2026-07-13: 얼굴 못잡네, 표정·움직임).
const FACE_MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";
const EXPR_KO: Record<string, string> = {
  smile: "웃는 표정", surprise: "놀란 표정", frown: "찡그린 표정",
  eyes_closed: "눈을 감음", mouth_open: "입을 벌림", neutral: "차분한 표정",
};
const HEAD_KO: Record<string, string> = {
  nodding: "고개 끄덕임", shaking: "고개 저음", turn_left: "고개 왼쪽으로",
  turn_right: "고개 오른쪽으로", look_up: "위를 봄", look_down: "아래를 봄", center: "정면 응시",
};
// distill 52 blendshapes → ONE honest expression (only the clearly-dominant one; else 차분한 표정).
function distillExpr(cats: { categoryName: string; score: number }[]): string {
  const s = (n: string) => cats.find((c) => c.categoryName === n)?.score ?? 0;
  const smile = (s("mouthSmileLeft") + s("mouthSmileRight")) / 2;
  const browDown = (s("browDownLeft") + s("browDownRight")) / 2;
  const blink = (s("eyeBlinkLeft") + s("eyeBlinkRight")) / 2;
  const jaw = s("jawOpen"), browUp = s("browInnerUp");
  if (smile > 0.45) return "smile";
  if (browUp > 0.45 && jaw > 0.22) return "surprise";
  if (browDown > 0.42) return "frown";
  if (blink > 0.55) return "eyes_closed";
  if (jaw > 0.45) return "mouth_open";
  return "neutral";
}
type FaceSample = { t: number; nx: number; ny: number };
// head movement from the nose's motion over ~1.4s — nodding (vertical to-and-fro), shaking
// (horizontal), or a sustained turn/tilt; else 정면.
function distillHead(hist: FaceSample[], nx: number, ny: number, cxEye: number, cyEye: number): string {
  const now = hist.length ? hist[hist.length - 1].t : 0;
  const w = hist.filter((h) => now - h.t < 1400);
  const rev = (vals: number[], j: number) => {
    let r = 0, d = 0;
    for (let i = 1; i < vals.length; i++) {
      const dv = vals[i] - vals[i - 1];
      if (Math.abs(dv) < j) continue;
      const nd = dv > 0 ? 1 : -1;
      if (d !== 0 && nd !== d) r++;
      d = nd;
    }
    return r;
  };
  if (w.length >= 5) {
    const xs = w.map((h) => h.nx), ys = w.map((h) => h.ny);
    if (rev(ys, 0.006) >= 2 && Math.max(...ys) - Math.min(...ys) > 0.03) return "nodding";
    if (rev(xs, 0.006) >= 2 && Math.max(...xs) - Math.min(...xs) > 0.03) return "shaking";
  }
  const dx = nx - cxEye, dy = ny - cyEye;                   // nose vs eye-center → gaze direction
  if (dx > 0.045) return "turn_left";                       // (mirrored selfie view)
  if (dx < -0.045) return "turn_right";
  if (dy < -0.02) return "look_up";
  if (dy > 0.06) return "look_down";
  return "center";
}

// Distill 33 MediaPipe pose landmarks → an HONEST posture/gesture. Only what's confidently
// visible is claimed (legs unseen → posture stays unknown, never guessed). Nothing but the
// distilled label leaves the page; the raw skeleton never does.
type Lm = { x: number; y: number; z: number; visibility?: number };
const POSTURE_KO: Record<string, string> = { standing: "서 있음", sitting: "앉아 있음", leaning: "몸을 기울임" };
const GESTURE_KO: Record<string, string> = {
  // static (single frame) — read from the 33 body landmarks (no fingers, so only whole-body poses)
  arms_raised: "양팔 듦", one_arm_raised: "한 팔 듦", hand_near_face: "손을 얼굴 가까이",
  t_pose: "양팔 벌림", stretching: "기지개", arms_crossed: "팔짱", hands_on_hips: "손 허리에",
  pointing: "가리킴", thinking: "턱을 괴고 생각",
  // dynamic (motion over time)
  waving: "손 흔들어 인사", clapping: "박수", beckoning: "손짓해 부름",
};

// A short motion history sample — the raised hand's x + the two-wrist gap, per frame.
type PoseSample = { t: number; wx: number; wy: number; gap: number; raised: boolean };
// Dynamic gestures need MOTION, not one frame: waving = a raised hand oscillating side-to-side;
// clapping = the wrist-gap opening and closing. We read the last ~1.4s of samples.
function detectDynamic(hist: PoseSample[]): string | null {
  if (hist.length < 5) return null;
  const now = hist[hist.length - 1].t;
  const w = hist.filter((s) => now - s.t < 1400);
  if (w.length < 5) return null;
  const reversals = (vals: number[], jitter: number) => {
    let rev = 0, dir = 0;
    for (let i = 1; i < vals.length; i++) {
      const dv = vals[i] - vals[i - 1];
      if (Math.abs(dv) < jitter) continue;
      const nd = dv > 0 ? 1 : -1;
      if (dir !== 0 && nd !== dir) rev++;
      dir = nd;
    }
    return rev;
  };
  // waving: hand raised most of the window + horizontal to-and-fro with real amplitude
  const raisedFrac = w.filter((s) => s.raised).length / w.length;
  if (raisedFrac > 0.6) {
    const xs = w.map((s) => s.wx);
    const amp = Math.max(...xs) - Math.min(...xs);
    if (reversals(xs, 0.012) >= 2 && amp > 0.06) return "waving";
  }
  // clapping: the two wrists come together and apart repeatedly (gap oscillates near closed)
  const gaps = w.map((s) => s.gap);
  if (Math.min(...gaps) < 0.13 && reversals(gaps, 0.01) >= 2) return "clapping";
  return null;
}
function distillPose(lm: Lm[]): { posture: string; gesture: string | null; present: boolean } {
  const vis = (i: number) => lm[i]?.visibility ?? 0;
  const d = (a: Lm, b: Lm) => Math.hypot(a.x - b.x, a.y - b.y);
  const [ls, rs, lw, rw, nose] = [lm[11], lm[12], lm[15], lm[16], lm[0]];
  const [lh, rh, lk, rk, la, ra] = [lm[23], lm[24], lm[25], lm[26], lm[27], lm[28]];
  const present = vis(11) > 0.5 || vis(12) > 0.5;
  const shoulderY = (ls.y + rs.y) / 2;
  const cx = (ls.x + rs.x) / 2;
  const hipY = (lh.y + rh.y) / 2;
  const sw = Math.abs(ls.x - rs.x) || 0.2;            // shoulder width (a scale for x thresholds)
  const chestY = (shoulderY + hipY) / 2;
  const noseY = nose?.y ?? shoulderY;
  const vw = (i: number) => vis(i) > 0.5;
  const lUp = vw(15) && lw.y < shoulderY - 0.05, rUp = vw(16) && rw.y < shoulderY - 0.05;
  // richer static gestures from body pose alone — most specific first (owner: 행동을 다양하게)
  let gesture: string | null = null;
  if (vw(15) && vw(16) && lw.y < noseY - 0.02 && rw.y < noseY - 0.02 && Math.abs(lw.x - rw.x) > sw * 1.3)
    gesture = "stretching";                                        // both hands high AND spread
  else if (lUp && rUp) gesture = "arms_raised";                    // both hands above shoulders
  else if (vw(15) && vw(16) && Math.abs(lw.y - shoulderY) < 0.1 && Math.abs(rw.y - shoulderY) < 0.1
           && Math.abs(lw.x - rw.x) > 0.5) gesture = "t_pose";     // arms out sideways
  else if (vw(0) && ((vw(15) && d(lw, nose) < 0.12) || (vw(16) && d(rw, nose) < 0.12)))
    gesture = "hand_near_face";                                    // hand at the face (턱 괴기 등)
  else if (vw(15) && vw(16) && Math.abs(lw.y - hipY) < 0.11 && Math.abs(rw.y - hipY) < 0.11)
    gesture = "hands_on_hips";                                     // both wrists at hip level
  else if (vw(15) && vw(16) && lw.y > shoulderY && rw.y > shoulderY && lw.y < chestY + 0.05
           && rw.y < chestY + 0.05 && Math.abs(lw.x - cx) < sw * 0.6 && Math.abs(rw.x - cx) < sw * 0.6)
    gesture = "arms_crossed";                                      // wrists folded across the chest
  else if (lUp !== rUp && (lUp || rUp)) gesture = "one_arm_raised"; // exactly one hand up
  else if ((vw(15) && Math.abs(lw.x - ls.x) > 0.26 && Math.abs(lw.y - shoulderY) < 0.14)
           || (vw(16) && Math.abs(rw.x - rs.x) > 0.26 && Math.abs(rw.y - shoulderY) < 0.14))
    gesture = "pointing";                                          // one arm extended horizontally
  let posture = "unknown";
  if (vis(23) > 0.5 && vis(25) > 0.5 && vis(27) > 0.5) {            // legs visible → real posture
    const hipY = (lh.y + rh.y) / 2, kneeY = (lk.y + rk.y) / 2;
    posture = kneeY <= hipY + 0.05 ? "sitting" : "standing";
    const sx = (ls.x + rs.x) / 2, hx = (lh.x + rh.x) / 2;
    if (Math.abs(sx - hx) > 0.13) posture = "leaning";
  }
  return { posture, gesture, present };
}

// COCO 라벨 → 한국어 (표면 번역표 — 지식이 아니라 표기)
const KO: Record<string, string> = {
  person: "사람", bottle: "물병", cup: "컵", chair: "의자", laptop: "노트북",
  "cell phone": "휴대폰", book: "책", keyboard: "키보드", mouse: "마우스",
  tv: "TV", clock: "시계", scissors: "가위", backpack: "가방", umbrella: "우산",
  "potted plant": "화분", vase: "꽃병", "wine glass": "유리잔", bowl: "그릇",
  banana: "바나나", apple: "사과", orange: "오렌지", cat: "고양이", dog: "개",
};

// A cheap, on-device VISUAL SIGNATURE for an object crop — a normalized RGB colour histogram
// (4×4×4 bins) + aspect ratio. Not an ML embedding: a genuine appearance fingerprint that needs
// no model download, computes in microseconds, and NEVER leaves the crop as pixels (only the
// 65-float histogram travels, to 127.0.0.1). The backend cross-checks it against past instances;
// its multi-view drift adaptation absorbs lighting/angle shift so the same bottle stays the same.
function signatureOf(v: HTMLVideoElement,
                     bb: { originX: number; originY: number; width: number; height: number },
                     canvas: HTMLCanvasElement): number[] {
  const S = 24;
  canvas.width = S; canvas.height = S;
  const g = canvas.getContext("2d", { willReadFrequently: true });
  if (!g || bb.width < 2 || bb.height < 2) return [];
  try {
    g.drawImage(v, bb.originX, bb.originY, bb.width, bb.height, 0, 0, S, S);
    const px = g.getImageData(0, 0, S, S).data;
    const bins = new Array(64).fill(0);                   // 4 levels per channel → 64 bins
    for (let i = 0; i < px.length; i += 4) {
      const r = px[i] >> 6, gg = px[i + 1] >> 6, b = px[i + 2] >> 6;   // 0..3 each
      bins[(r << 4) | (gg << 2) | b]++;
    }
    const tot = px.length / 4 || 1;
    const sig = bins.map((c) => c / tot);
    sig.push(Math.min(2, bb.width / (bb.height || 1)) / 2);           // aspect ratio → ~[0,1]
    return sig;
  } catch {
    return [];                                            // tainted canvas / cross-origin → honest empty
  }
}

// Dominant HUE of an object crop (0..360, or -1 when the crop is essentially grey). The audit's
// next lesson: a red bottle should replay red, not a label-hashed colour. Saturation-weighted so
// washed-out pixels don't vote; reuses the same offscreen canvas as the signature. On-device; only
// the single number leaves. -1 → no confident colour, so the backend keeps the honest label hue.
function hueOf(v: HTMLVideoElement,
               bb: { originX: number; originY: number; width: number; height: number },
               canvas: HTMLCanvasElement): number {
  const S = 24;
  const g = canvas.getContext("2d", { willReadFrequently: true });
  if (!g || bb.width < 2 || bb.height < 2) return -1;
  try {
    canvas.width = S; canvas.height = S;
    g.drawImage(v, bb.originX, bb.originY, bb.width, bb.height, 0, 0, S, S);
    const px = g.getImageData(0, 0, S, S).data;
    let sx = 0, sy = 0, wsum = 0;                        // circular-mean of hue, weighted by sat×val
    for (let i = 0; i < px.length; i += 4) {
      const r = px[i] / 255, gg = px[i + 1] / 255, b = px[i + 2] / 255;
      const mx = Math.max(r, gg, b), mn = Math.min(r, gg, b), d = mx - mn;
      if (d < 0.08) continue;                            // grey pixel — no hue to vote with
      let h = 0;
      if (mx === r) h = ((gg - b) / d) % 6;
      else if (mx === gg) h = (b - r) / d + 2;
      else h = (r - gg) / d + 4;
      h *= 60; if (h < 0) h += 360;
      const w = d * mx;                                  // saturation × value
      const a = (h * Math.PI) / 180;
      sx += Math.cos(a) * w; sy += Math.sin(a) * w; wsum += w;
    }
    if (wsum < 0.5) return -1;                           // mostly grey → no confident colour
    let h = (Math.atan2(sy, sx) * 180) / Math.PI;
    return h < 0 ? h + 360 : h;
  } catch {
    return -1;
  }
}

type Sighting = { label: string; score: number; at: number };
type Suggestion = { object: string; age_days: number; suggestion: string };
type Reunion = { label: string; times: number; at: number };
type Face = { identity: string | null; familiarity: number; emotion: string | null;
              age: number | null; embedding?: number[] };

export default function PerceptionPage() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const grabRef = useRef<HTMLCanvasElement | null>(null);
  const [phase, setPhase] = useState<"boot" | "camera" | "model" | "live" | "denied" | "failed">("boot");
  const [sightings, setSightings] = useState<Sighting[]>([]);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [detail, setDetail] = useState("");
  const [faces, setFaces] = useState<Face[]>([]);
  const [faceCore, setFaceCore] = useState<"unknown" | "present" | "absent">("unknown");
  const [pose, setPose] = useState<{ posture: string; gesture: string | null } | null>(null);
  // on-device face read: presence + expression + head movement (MediaPipe, no frame leaves)
  const [faceRead, setFaceRead] = useState<{ expr: string; head: string } | null>(null);
  const detectionsRef = useRef<{ label: string; x: number; y: number; depth: number;
                                 size: number; hue: number; signature: number[] }[]>([]);
  const lastSnapSigRef = useRef("");
  const [spatialSaved, setSpatialSaved] = useState(0);
  const [reunions, setReunions] = useState<Reunion[]>([]);
  // SCENE WEAVE — 목록("사람 85%")이 아니라 살아있는 맥락 문장. 서버(OWLv2+씬그래프+직물)가
  // 첫눈엔 장면 전체를, 그 후엔 변화가 있을 때만 새 문장을 돌려준다.
  type SceneObj = { label_ko: string; box: number[]; score: number; color: string;
                    tentative?: boolean; reverify_reason?: string | null };
  type SceneRead = { living: string; relations: string[]; commonsense: string | null;
                     objects: SceneObj[]; size: number[]; changedAt?: number };
  const [scene, setScene] = useState<SceneRead | null>(null);
  const overlayRef = useRef<HTMLCanvasElement | null>(null);
  const sceneBusyRef = useRef(false);

  useEffect(() => {
    let stop = false;
    let stream: MediaStream | null = null;
    let timer: ReturnType<typeof setInterval> | null = null;
    let faceTimer: ReturnType<typeof setInterval> | null = null;
    let faceTimer2: ReturnType<typeof setInterval> | null = null;
    let poseTimer: ReturnType<typeof setInterval> | null = null;
    let snapTimer: ReturnType<typeof setInterval> | null = null;
    let sceneTimer: ReturnType<typeof setInterval> | null = null;
    (async () => {
      // 1) camera (rear preferred; desktop falls back to any)
      setPhase("camera");
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" } }, audio: false,
        });
      } catch {
        setPhase("denied");
        return;
      }
      if (stop || !videoRef.current) return;
      videoRef.current.srcObject = stream;
      await videoRef.current.play().catch(() => {});

      // 2) on-device detector (WASM CNN via CDN — bundler-opaque dynamic import)
      setPhase("model");
      type Det = { categories: { categoryName: string; score: number }[];
                   boundingBox?: { originX: number; originY: number; width: number; height: number } };
      let detector: { detectForVideo: (v: HTMLVideoElement, t: number) => { detections: Det[] } };
      try {
        const importUrl = new Function("u", "return import(u)");
        const vision = await importUrl(MP_URL);
        const fileset = await vision.FilesetResolver.forVisionTasks(`${MP_URL}/wasm`);
        detector = await vision.ObjectDetector.createFromOptions(fileset, {
          baseOptions: { modelAssetPath: MODEL_URL },
          scoreThreshold: 0.5,
          runningMode: "VIDEO",
        });
      } catch (e) {
        setDetail(String(e).slice(0, 140));
        setPhase("failed");
        return;
      }
      if (stop) return;
      setPhase("live");

      // 3) detect ~1.5s cadence; ONLY labels leave this page
      const seen = new Map<string, number>();
      const sigCanvas = document.createElement("canvas");   // offscreen, for object signatures
      timer = setInterval(async () => {
        const v = videoRef.current;
        if (!v || v.readyState < 2) return;
        let dets: Det[] = [];
        try {
          dets = detector.detectForVideo(v, performance.now()).detections || [];
        } catch { return; }
        // capture the CURRENT scene's objects with normalized bbox centers (for spatial memory) and
        // a visual signature (for re-recognition). Only [0,1] positions + the histogram leave; the
        // 3D transform (unit cube + Y-flip) and the identity matching live in the backend.
        const vw = v.videoWidth || 1, vh = v.videoHeight || 1;
        detectionsRef.current = dets
          .filter((d) => (d.categories?.[0]?.score ?? 0) >= 0.5 && d.boundingBox)
          .map((d) => {
            const bb = d.boundingBox!;
            return {
              label: KO[d.categories[0].categoryName] || d.categories[0].categoryName,
              x: Math.max(0, Math.min(1, (bb.originX + bb.width / 2) / vw)),
              y: Math.max(0, Math.min(1, (bb.originY + bb.height / 2) / vh)),
              depth: Math.max(0, Math.min(1, 1 - (bb.height / vh) * 1.5)),   // bigger = nearer → depth→0
              size: Math.max(0, Math.min(1, (bb.width * bb.height) / (vw * vh))),  // audit-named lesson
              hue: hueOf(v, bb, sigCanvas),                // dominant colour (audit's next lesson)
              signature: signatureOf(v, bb, sigCanvas),
            };
          });
        const now = Date.now();
        const fresh: Sighting[] = [];
        for (const d of dets) {
          const c = d.categories?.[0];
          if (!c || c.score < 0.5) continue;
          const label = KO[c.categoryName] || c.categoryName;
          if (now - (seen.get(label) || 0) < 30_000) continue; // page-side cooldown
          seen.set(label, now);
          fresh.push({ label, score: c.score, at: now });
        }
        if (!fresh.length) return;
        setSightings((prev) => [...fresh, ...prev].slice(0, 12));
        try {
          const r = await fetch("/api/perception/visual-ingest", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ detections: fresh.map((f) => ({ label: f.label, score: f.score })) }),
          });
          const out = await r.json();
          if (out?.suggestions?.length) {
            setSuggestions((prev) => {
              const known = new Set(prev.map((s) => s.object));
              return [...prev, ...out.suggestions.filter((s: Suggestion) => !known.has(s.object))].slice(-4);
            });
          }
        } catch { /* server offline: sightings stay page-local */ }
      }, 1500);

      // 4) FACE cortex — grab a downscaled frame ~every 2.2s and send it to the LOCAL engine,
      // which runs DeepFace and returns a DISTILLED perception (identity or honest gap + state).
      // The frame is never stored anywhere; only the perception comes back.
      faceTimer = setInterval(async () => {
        const v = videoRef.current;
        const c = grabRef.current;
        if (!v || !c || v.readyState < 2) return;
        c.width = 320; c.height = Math.round((v.videoHeight / v.videoWidth) * 320) || 240;
        const g = c.getContext("2d");
        if (!g) return;
        g.drawImage(v, 0, 0, c.width, c.height);
        let image = "";
        try { image = c.toDataURL("image/jpeg", 0.7); } catch { return; }
        try {
          const r = await fetch("/api/perception/face-ingest", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ image }),
          });
          const out = await r.json();
          if (out?.core === "absent") { setFaceCore("absent"); setFaces([]); return; }
          setFaceCore("present");
          setFaces(Array.isArray(out?.faces) ? out.faces : []);
        } catch { /* engine offline → face read pauses */ }
      }, 2200);

      // 5) POSE cortex — MediaPipe Pose runs IN THE BROWSER. We distill 33 landmarks to an
      // honest posture/gesture and send only that (never the skeleton, never a frame), and
      // only when it CHANGES — the timeline stays a life log, not a pose log.
      try {
        const importUrl = new Function("u", "return import(u)");
        const vision = await importUrl(MP_URL);
        const fileset = await vision.FilesetResolver.forVisionTasks(`${MP_URL}/wasm`);
        const poser = await vision.PoseLandmarker.createFromOptions(fileset, {
          baseOptions: { modelAssetPath: POSE_MODEL_URL },
          runningMode: "VIDEO",
          numPoses: 1,
        });
        let lastSent = "";
        const hist: PoseSample[] = [];             // short motion memory for dynamic gestures
        poseTimer = setInterval(async () => {
          const v = videoRef.current;
          if (!v || v.readyState < 2) return;
          let res: { landmarks?: Lm[][] };
          try { res = poser.detectForVideo(v, performance.now()); } catch { return; }
          const lm = res.landmarks?.[0];
          if (!lm || lm.length < 29) { setPose(null); hist.length = 0; return; }
          const dp = distillPose(lm);
          if (!dp.present) { setPose(null); hist.length = 0; return; }
          // sample the raised hand's motion so waving/clapping can emerge over time
          const shoulderY = ((lm[11]?.y ?? 0) + (lm[12]?.y ?? 0)) / 2;
          const lw = lm[15], rw = lm[16];
          const hi = (lw?.y ?? 1) < (rw?.y ?? 1) ? lw : rw;      // the higher (raised) hand
          const t = performance.now();
          hist.push({ t, wx: hi?.x ?? 0, wy: hi?.y ?? 0,
                      gap: Math.abs((lw?.x ?? 0) - (rw?.x ?? 0)), raised: (hi?.y ?? 1) < shoulderY });
          while (hist.length && t - hist[0].t > 2000) hist.shift();
          const gesture = detectDynamic(hist) ?? dp.gesture;    // motion wins over a static pose
          setPose({ posture: dp.posture, gesture });
          const sig = `${dp.posture}|${gesture ?? ""}`;
          if (sig === lastSent) return;                          // send only on a distilled change
          lastSent = sig;
          try {
            await fetch("/api/perception/pose-ingest", {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ posture: dp.posture, gesture, present: dp.present }),
            });
          } catch { /* engine offline → posture stays page-local */ }
        }, 220);
      } catch { /* pose model failed to load → face + objects still run */ }

      // 5b) FACE landmarker — IN-BROWSER, so it reliably catches the face DeepFace missed, and reads
      // EXPRESSION (blendshapes) + head MOVEMENT. Nothing but the distilled label ever surfaces; no
      // frame, no landmark, no blendshape leaves the page. Runs ~every 260ms.
      try {
        const importUrl = new Function("u", "return import(u)");
        const vision = await importUrl(MP_URL);
        const fileset = await vision.FilesetResolver.forVisionTasks(`${MP_URL}/wasm`);
        const faceLm = await vision.FaceLandmarker.createFromOptions(fileset, {
          baseOptions: { modelAssetPath: FACE_MODEL_URL },
          runningMode: "VIDEO", numFaces: 1, outputFaceBlendshapes: true,
        });
        const fhist: FaceSample[] = [];
        let lastFaceSig = "";
        faceTimer2 = setInterval(() => {
          const v = videoRef.current;
          if (!v || v.readyState < 2) return;
          let res: { faceLandmarks?: Lm[][]; faceBlendshapes?: { categories: { categoryName: string; score: number }[] }[] };
          try { res = faceLm.detectForVideo(v, performance.now()); } catch { return; }
          const lm = res.faceLandmarks?.[0];
          const bs = res.faceBlendshapes?.[0]?.categories;
          if (!lm || lm.length < 400) { setFaceRead(null); fhist.length = 0; return; }
          const nose = lm[1], le = lm[263], re = lm[33];
          const t = performance.now();
          fhist.push({ t, nx: nose?.x ?? 0, ny: nose?.y ?? 0 });
          while (fhist.length && t - fhist[0].t > 1600) fhist.shift();
          const expr = bs ? distillExpr(bs) : "neutral";
          const head = distillHead(fhist, nose?.x ?? 0, nose?.y ?? 0,
                                   ((le?.x ?? 0) + (re?.x ?? 0)) / 2, ((le?.y ?? 0) + (re?.y ?? 0)) / 2);
          setFaceRead({ expr, head });
          const sig = `${expr}|${head}`;
          if (sig === lastFaceSig) return;                   // only on a distilled change
          lastFaceSig = sig;
          fetch("/api/perception/pose-ingest", {              // reuse the distilled-signal lane
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ posture: "face", gesture: `${expr}:${head}`, present: true }),
          }).catch(() => {});
        }, 260);
      } catch { /* face model failed → identity(DeepFace) + objects + pose still run */ }

      // 6) SPATIAL MEMORY — every ~4s, if the SCENE changed, remember WHERE things are (positions
      // only, never a frame) so the space can be replayed later. A memory of rooms, not a frame log.
      snapTimer = setInterval(async () => {
        const objs = detectionsRef.current;
        if (!objs.length) return;
        const sig = objs.map((o) => o.label).sort().join("|");
        if (sig === lastSnapSigRef.current) return;          // only on a changed layout
        lastSnapSigRef.current = sig;
        try {
          const r = await fetch("/api/perception/spatial-snapshot", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ objects: objs }),
          });
          const out = await r.json();
          if (out?.recorded) setSpatialSaved((n) => n + 1);
          // objects the eye RE-RECOGNIZED (seen before) — surface them so the memory is visible
          const back: Reunion[] = (out?.recognized || [])
            .filter((x: { matched?: boolean; times_seen?: number }) => x.matched && (x.times_seen ?? 0) >= 2)
            .map((x: { label: string; times_seen?: number }) =>
              ({ label: x.label, times: x.times_seen ?? 2, at: Date.now() }));
          if (back.length) setReunions((prev) => [...back, ...prev].slice(0, 4));
        } catch { /* engine offline → the space stays unremembered, honestly */ }
      }, 4000);

      // 7) SCENE WEAVE — every ~3.2s a downscaled frame goes to the LOCAL engine's open-vocabulary
      // eye(OWLv2). 돌아오는 건 접지된 장면 읽기: 사물+박스+색, 관계, 그리고 '살아있는 문장' —
      // 첫눈엔 장면 전체를, 그 후엔 변화가 있을 때만 새로 말한다(사람이 보는 방식). 프레임은
      // 로컬 엔진에서 증류 후 즉시 버려진다(127.0.0.1 밖으로 안 나감).
      sceneTimer = setInterval(async () => {
        if (sceneBusyRef.current) return;                    // OWLv2 ~1s — 요청 겹침 방지
        const v = videoRef.current, c = grabRef.current;
        if (!v || !c || v.readyState < 2) return;
        c.width = 480; c.height = Math.round((v.videoHeight / v.videoWidth) * 480) || 360;
        const g = c.getContext("2d");
        if (!g) return;
        g.drawImage(v, 0, 0, c.width, c.height);
        let image = "";
        try { image = c.toDataURL("image/jpeg", 0.72); } catch { return; }
        sceneBusyRef.current = true;
        try {
          const r = await fetch("/api/perception/scene-ingest", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ image }),
          });
          const out = await r.json();
          if (out?.core === "owlv2" && Array.isArray(out.objects)) {
            setScene((prev) => ({
              living: out.living_sentence || out.scene_sentence || prev?.living || "",
              relations: Array.isArray(out.relations_ko) ? out.relations_ko : [],
              commonsense: out.commonsense || null,
              objects: out.objects,
              size: Array.isArray(out.image_size) ? out.image_size : [c.width, c.height],
              changedAt: out.changed ? Date.now() : prev?.changedAt,
            }));
          }
        } catch { /* engine offline → 장면 이야기는 정직하게 멈춘다 */ }
        finally { sceneBusyRef.current = false; }
      }, 3200);
    })();
    return () => {
      stop = true;
      if (timer) clearInterval(timer);
      if (faceTimer) clearInterval(faceTimer);
      if (faceTimer2) clearInterval(faceTimer2);
      if (poseTimer) clearInterval(poseTimer);
      if (snapTimer) clearInterval(snapTimer);
      if (sceneTimer) clearInterval(sceneTimer);
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  // colored-box overlay — 서버가 읽어준 사물들을 각자 고유 색으로 화면 위에 그린다(사장님: "다
  // 표기"). video는 objectFit:cover라 같은 cover 변환(scale=max, 중앙 오프셋)으로 좌표를 사상한다.
  useEffect(() => {
    const cv = overlayRef.current;
    if (!cv) return;
    const cw = cv.clientWidth || window.innerWidth;
    const ch = cv.clientHeight || window.innerHeight;
    cv.width = cw; cv.height = ch;
    const g = cv.getContext("2d");
    if (!g) return;
    g.clearRect(0, 0, cw, ch);
    if (!scene?.objects?.length) return;
    const [iw, ih] = scene.size[0] > 0 ? scene.size : [480, 360];
    const s = Math.max(cw / iw, ch / ih);
    const dx = (cw - iw * s) / 2, dy = (ch - ih * s) / 2;
    g.font = "600 13px ui-monospace, monospace";
    for (const o of scene.objects) {
      if (!Array.isArray(o.box) || o.box.length < 4) continue;
      const rx = o.box[0] * s + dx, ry = o.box[1] * s + dy;
      const rw = (o.box[2] - o.box[0]) * s, rh = (o.box[3] - o.box[1]) * s;
      // tentative(재확인 중) objects are drawn dimmed + dashed until re-verified — a confident box is solid
      g.strokeStyle = o.color; g.lineWidth = o.tentative ? 1.5 : 2.5;
      g.globalAlpha = o.tentative ? 0.5 : 1;
      g.setLineDash(o.tentative ? [6, 5] : []);
      g.strokeRect(rx, ry, rw, rh);
      g.setLineDash([]);
      const label = o.tentative ? `${o.label_ko}? 재확인` : `${o.label_ko} ${Math.round(o.score * 100)}%`;
      const tw = g.measureText(label).width + 10;
      g.fillStyle = "rgba(5,7,10,0.78)";
      g.fillRect(rx, Math.max(0, ry - 20), tw, 20);
      g.fillStyle = o.color;
      g.fillText(label, rx + 5, Math.max(13, ry - 6));
      g.globalAlpha = 1;
    }
  }, [scene]);

  // teach a NAME to a face the cortex just saw but didn't recognize — the only path a name
  // enters. Purely local; the embedding is a geometric signature, not a photo.
  async function teachFace(embedding: number[] | undefined) {
    if (!embedding || !embedding.length) return;
    const name = window.prompt("이 사람이 누구인가요? (이름을 알려주면 다음엔 알아봐요)")?.trim();
    if (!name) return;
    try {
      await fetch("/api/perception/face-teach", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, embedding }),
      });
      setFaces((prev) => prev.map((f) => (f.embedding === embedding
        ? { ...f, identity: name, familiarity: 1 } : f)));
    } catch { /* engine offline */ }
  }

  const hudBox: React.CSSProperties = {
    background: "rgba(10,15,25,0.82)", padding: "14px 18px", borderRadius: 8,
    border: "1px solid rgba(56,189,248,0.25)", backdropFilter: "blur(10px)",
    fontFamily: "ui-monospace, monospace", fontSize: 13, color: "#e2e8f0",
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "#05070A", overflow: "hidden" }}>
      <video ref={videoRef} playsInline muted
             style={{ position: "absolute", inset: 0, width: "100%", height: "100%",
                      objectFit: "cover", opacity: phase === "live" ? 0.9 : 0.25 }} />
      <canvas ref={grabRef} style={{ display: "none" }} />
      {/* 오픈보캐뷸러리 눈이 읽은 사물들 — 색깔 박스 + 한국어 라벨 오버레이 */}
      <canvas ref={overlayRef} style={{ position: "absolute", inset: 0, width: "100%",
                                        height: "100%", pointerEvents: "none" }} />

      {/* 지금 보는 맥락 — 살아있는 문장. 첫눈엔 장면 전체, 그 후엔 변화가 있을 때만 바뀐다. */}
      {phase === "live" && scene?.living && (
        <div style={{ position: "absolute", left: "50%", bottom: 26, transform: "translateX(-50%)",
                      maxWidth: "min(880px, 92vw)", textAlign: "center", ...hudBox,
                      border: "1px solid rgba(255,138,0,0.38)", padding: "14px 24px" }}>
          <div style={{ fontSize: 11, letterSpacing: "0.24em", color: "#ff8a00", marginBottom: 6 }}>
            지금 보는 맥락
          </div>
          <div style={{ fontSize: 16.5, lineHeight: 1.55, color: "#f8fafc" }}>{scene.living}</div>
          {(scene.relations.length > 0 || scene.commonsense) && (
            <div style={{ marginTop: 7, fontSize: 12, opacity: 0.72, lineHeight: 1.5 }}>
              {scene.relations.slice(0, 3).join(" · ")}
              {scene.commonsense ? `${scene.relations.length ? " · " : ""}${scene.commonsense}` : ""}
            </div>
          )}
        </div>
      )}

      {/* 시각 피질 — 얼굴/사람 인지. 프레임은 저장하지 않고, 알아본 사람(또는 정직한 '처음 봄')과
          상태만 돌아옵니다. 모르는 얼굴엔 이름을 지어내지 않고, 알려주면 그때부터 기억합니다. */}
      {phase === "live" && (
        <div style={{ position: "absolute", top: 20, right: 22, maxWidth: 320, ...hudBox,
                      border: "1px solid rgba(210,82,31,0.35)" }}>
          <div style={{ letterSpacing: "0.2em", color: "#ff8a00", fontWeight: 700, marginBottom: 8 }}>
            카메라 인식 · 얼굴 · 자세
          </div>
          {faceCore === "absent" && (
            <div style={{ opacity: 0.7, fontSize: 12 }}>
              얼굴 인식 코어(DeepFace)가 아직 설치되지 않았어요 — 지금은 얼굴을 못 봅니다.
              눈은 준비됐고, 코어만 올리면 바로 알아봅니다.
            </div>
          )}
          {faceCore === "present" && faces.length === 0 && (
            <div style={{ opacity: 0.6, fontSize: 12 }}>지금 화면엔 얼굴이 안 보여요.</div>
          )}
          {faces.map((f, i) => (
            <div key={i} style={{ marginBottom: 8 }}>
              {f.identity ? (
                <div style={{ color: "#e2e8f0" }}>
                  <span style={{ color: "#ff8a00", fontWeight: 700 }}>{f.identity}</span>
                  {f.emotion ? <span style={{ opacity: 0.7 }}> · {f.emotion}</span> : null}
                  <span style={{ opacity: 0.45, fontSize: 11 }}> ({(f.familiarity * 100).toFixed(0)}%)</span>
                </div>
              ) : (
                <div>
                  <div style={{ opacity: 0.85 }}>처음 보는 얼굴 — 아직 누구인지 몰라요.</div>
                  <button onClick={() => teachFace(f.embedding)} style={{
                    marginTop: 5, background: "rgba(255,138,0,0.16)", color: "#ff8a00",
                    border: "1px solid rgba(255,138,0,0.4)", borderRadius: 7, padding: "5px 10px",
                    fontSize: 12, cursor: "pointer", fontFamily: "inherit" }}>
                    이 사람 알려주기
                  </button>
                </div>
              )}
            </div>
          ))}
          {faceRead && (
            <div style={{ marginTop: 10, paddingTop: 8, borderTop: "1px solid rgba(255,255,255,0.12)" }}>
              <div style={{ letterSpacing: "0.15em", color: "#38bdf8", fontSize: 11, marginBottom: 4 }}>
                표정 · 얼굴 움직임 <span style={{ opacity: 0.4 }}>(온디바이스)</span>
              </div>
              <div style={{ color: "#e2e8f0" }}>
                <span>{EXPR_KO[faceRead.expr] || faceRead.expr}</span>
                {faceRead.head !== "center" && (
                  <span style={{ color: "#ff8a00" }}> · {HEAD_KO[faceRead.head] || faceRead.head}</span>
                )}
              </div>
            </div>
          )}
          {pose && (pose.posture !== "unknown" || pose.gesture) && (
            <div style={{ marginTop: 10, paddingTop: 8, borderTop: "1px solid rgba(255,255,255,0.12)" }}>
              <div style={{ letterSpacing: "0.15em", color: "#38bdf8", fontSize: 11, marginBottom: 4 }}>
                자세 · 제스처
              </div>
              <div style={{ color: "#e2e8f0" }}>
                {pose.posture !== "unknown" && <span>{POSTURE_KO[pose.posture] || pose.posture}</span>}
                {pose.gesture && (
                  <span style={{ color: "#ff8a00" }}>
                    {pose.posture !== "unknown" ? " · " : ""}{GESTURE_KO[pose.gesture] || pose.gesture}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      )}
      <div style={{ position: "absolute", top: 20, left: 22, maxWidth: 360, ...hudBox }}>
        <div style={{ letterSpacing: "0.2em", color: "#38bdf8", fontWeight: 700, marginBottom: 8 }}>
          실시간 지각 스트림 v0
        </div>
        {phase === "camera" && <div style={{ opacity: 0.7 }}>카메라 권한을 기다리는 중…</div>}
        {phase === "model" && <div style={{ opacity: 0.7 }}>온디바이스 감지 모델을 여는 중… (프레임은 이 페이지 밖으로 나가지 않습니다)</div>}
        {phase === "denied" && <div style={{ opacity: 0.7 }}>카메라 권한이 없어 지각이 꺼져 있어요. 허용하면 이 기기 안에서만 감지합니다.</div>}
        {phase === "failed" && <div style={{ opacity: 0.7 }}>감지 모델을 불러오지 못했습니다 (네트워크/CDN). {detail}</div>}
        {phase === "live" && (
          <>
            <div style={{ opacity: 0.75, marginBottom: 6 }}>
              가벼운 감지는 기기 안(WASM), 장면·얼굴 프레임은 로컬 엔진(127.0.0.1)에서
              증류 후 즉시 버려집니다 — 저장도, 외부 전송도 없습니다.
            </div>
            <div style={{ opacity: 0.55, fontSize: 11 }}>
              본 것은 에피소드 타임라인에 기록되고, 근거가 쌓인 만큼만 제안이 옵니다.
            </div>
            <div style={{ marginTop: 10, paddingTop: 8, borderTop: "1px solid rgba(255,255,255,0.1)",
              display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
              <span style={{ fontSize: 11.5, color: "#38bdf8" }}>
                공간 기억 · {spatialSaved}개 방 기록됨
                <span style={{ opacity: 0.5, fontSize: 10, display: "block" }}>배치만 저장, 프레임은 안 남김</span>
              </span>
              <a href="/imagination?replay=1" style={{ fontSize: 11.5, color: "#ff8a00",
                textDecoration: "none", border: "1px solid rgba(255,138,0,0.4)", borderRadius: 7,
                padding: "4px 9px", whiteSpace: "nowrap" }}>기억 재생 →</a>
            </div>
            {reunions.length > 0 && (
              <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid rgba(255,255,255,0.1)" }}>
                <div style={{ fontSize: 11, color: "#ff8a00", letterSpacing: "0.12em", marginBottom: 3 }}>
                  다시 알아봄
                </div>
                {reunions.map((r, i) => (
                  <div key={i} style={{ display: "flex", justifyContent: "space-between",
                    fontSize: 12, opacity: 0.9 }}>
                    <span>{r.label}</span>
                    <span style={{ color: "#38bdf8" }}>{r.times}번째 봄</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
        {sightings.length > 0 && (
          <div style={{ marginTop: 10 }}>
            {sightings.slice(0, 6).map((s, i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", opacity: 0.85 }}>
                <span>{s.label}</span>
                <span style={{ color: "#38bdf8" }}>{(s.score * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        )}
      </div>
      {suggestions.map((s, i) => (
        <div key={s.object} style={{
          position: "absolute", bottom: 26 + i * 86, left: "50%", transform: "translateX(-50%)",
          maxWidth: 460, ...hudBox, border: "1px solid rgba(210,82,31,0.5)",
        }}>
          <div style={{ color: "#d2521f", fontWeight: 700, marginBottom: 4 }}>제안 — 기록에 근거함</div>
          <div>{s.suggestion}</div>
          <div style={{ opacity: 0.5, fontSize: 11, marginTop: 4 }}>근거: {s.object} 관련 기록 {s.age_days}일 전</div>
        </div>
      ))}
    </div>
  );
}
