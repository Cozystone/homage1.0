"use client";

// SPLATRA 파티클 엔진 — 네이티브 이식. 스튜디오 화면은 버리고 렌더 코어만
// ATANOR 앱 안에서 산다: 이방성 3DGS EWA 스플래팅, 16비트 카운팅 깊이정렬,
// 마이크로봇 flow, 학습 리그 FK 스키닝, 물/흙 재질, 눈 깜빡임(부위 채널),
// 감정 구동은 기계 캐릭터(avatar)일 때만. 모든 서버 통신은 /api/splatra 프록시.
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";

export type SplatraHandle = {
  animate: (style: string) => void;
  gesture: (name: string) => void;      // wave etc. — moves ONE limb, no reload
  reload: () => void;
  disassemble: () => void;
};

const API = "/api/splatra";

const VERT = `#version 300 es
precision highp float;
layout(location=0) in vec2 aCorner;
layout(location=1) in uint aIndex;
uniform sampler2D uData; uniform int uTexW;
uniform mat4 uProj, uView; uniform vec2 uFocal, uViewport;
uniform float uT, uSizeScale, uModelScale, uSwirl;
uniform vec3 uModelCenter;
uniform int uAnimMode; uniform float uAnimT, uAnimAmp;
uniform int uNJ;
uniform vec3 uJPos[16]; uniform vec3 uJOut[16]; uniform float uJReach;
uniform mat3 uJRot[16]; uniform vec3 uJTrans[16];
uniform int uNEye; uniform vec4 uEyes[4];
uniform float uBlink;
uniform float uFloorY;
out vec3 vColor; out float vOpacity; out vec2 vQuad;
vec4 texel(int p){ return texelFetch(uData, ivec2(p % uTexW, p / uTexW), 0); }
vec3 hash3(vec3 p){ p = fract(p*vec3(443.897,441.423,437.195)); p += dot(p, p.yzx+19.19); return fract((p.xxy+p.yzz)*p.zyx); }
void main(){
  int base = int(aIndex)*4;
  vec4 t0 = texel(base), t1 = texel(base+1), t2 = texel(base+2), t3 = texel(base+3);
  vec3 home = t0.xyz; float opacity = t0.w; vec3 color = t1.xyz;

  // assembly: pieces blow in like WIND (owner spec) — staggered per particle
  // from one side, each settling into place under the continuous Y-spin
  vec3 h = hash3(home + 0.123);
  float e = smoothstep(0.0, 1.0, clamp((uT - h.y*0.45) / 0.55, 0.0, 1.0));
  e = e*e*(3.0-2.0*e);
  vec3 wind = vec3(2.6 + 1.8*h.x, 0.9*(h.z-0.2), 1.4*(h.y-0.5));
  vec3 scatter = home + wind + (h - 0.5)*1.6;
  vec3 pos = mix(scatter, home, e);
  float ca = cos(uSwirl), sa = sin(uSwirl);
  pos.xz = mat2(ca, -sa, sa, ca) * pos.xz;

  if (uAnimMode == 10) {              // microbot flow: always gently alive
    float ff = 2.3, aA = uAnimAmp, ph = uAnimT;
    vec3 q = home*ff + vec3(ph*0.6, ph*0.5, ph*0.7);
    vec3 fl = vec3(sin(q.y)*cos(q.z), sin(q.z)*cos(q.x), sin(q.x)*cos(q.y));
    fl.x += 0.25*sin(ph*0.30 + home.y*1.5);
    fl.y += 0.25*cos(ph*0.27 + home.z*1.5);
    fl.z += 0.25*sin(ph*0.33 + home.x*1.5);
    // owner: the body read as WOBBLY — the flow is a faint shimmer, not a melt
    pos += fl * (0.018 * aA);
  }
  if (uAnimMode == 11 && uNJ > 0) {   // learned rig: true FK, matrices from JS
    int bj = -1; float bd = 1e9; float bproj = 0.0;
    for (int k = 0; k < 16; k++) {
      if (k >= uNJ) break;
      float proj = dot(home - uJPos[k], uJOut[k]);
      if (proj > 0.0) { float dd = distance(home, uJPos[k]);
        if (dd < bd) { bd = dd; bj = k; bproj = proj; } }
    }
    if (bj >= 0) {
      float w = smoothstep(0.0, uJReach*0.5, bproj);
      vec3 posed = uJRot[bj]*home + uJTrans[bj];
      pos += (posed - home) * (w * uAnimAmp);
    }
  }
  if (uAnimMode == 12) {              // water: dissolve to a rippling puddle
    float m = uAnimAmp; vec3 hh = hash3(home*3.7);
    float fall = smoothstep(0.0, 1.0, m*1.35 - hh.x*0.35);
    float py = uFloorY + 0.02 + hh.x*0.05;
    vec3 dirout = normalize(vec3(home.x, 0.0, home.z) + vec3(1e-4));
    vec3 puddle = vec3(home.x, py, home.z) + dirout*(0.55 + 0.7*hh.y)*fall;
    puddle.x += 0.04*sin(uAnimT*1.7 + home.z*9.0);
    puddle.z += 0.04*cos(uAnimT*1.5 + home.x*9.0);
    pos = mix(pos, puddle, fall);
  }
  if (uAnimMode == 13) {              // soil: crumble into a settled mound
    float m = uAnimAmp; vec3 hh = hash3(home*5.1);
    float p = clamp((m*1.5 - hh.x*0.8)/0.5, 0.0, 1.0);
    p = p*p*(3.0-2.0*p);
    float pile = uFloorY + 0.02 + hh.y*hh.y*0.30;
    vec3 crumb = vec3(home.x*(1.0+0.25*p*hh.z), pile, home.z*(1.0+0.25*p*hh.x));
    crumb.x += 0.015*sin(uAnimT*0.8 + hh.y*20.0)*p;
    pos = mix(pos, crumb, p);
  }
  if (uNEye > 0 && uBlink > 0.001) {  // blink: only eye particles move
    for (int ey = 0; ey < 4; ey++) {
      if (ey >= uNEye) break;
      float dd = distance(home, uEyes[ey].xyz);
      float inEye = 1.0 - smoothstep(uEyes[ey].w*0.85, uEyes[ey].w*1.25, dd);
      if (inEye > 0.0) {
        float lid = uEyes[ey].xyz.y + uEyes[ey].w*(1.0 - 2.0*uBlink);
        pos.y -= max(0.0, home.y - lid) * inEye * 0.92;
      }
    }
  }

  // normalize EVERY generated model to the same framed size (피카츄는 예시 —
  // this must hold for anything the generator emits): center + fit-scale are
  // computed on upload, applied after posing so the rig math stays in
  // home coordinates.
  pos = (pos - uModelCenter) * uModelScale;
  vec4 cam = uView * vec4(pos,1.0);
  if (cam.z >= -0.05) { gl_Position = vec4(2.0,2.0,2.0,1.0); return; }
  vec4 clip = uProj * cam;
  float ss = uSizeScale*uSizeScale;
  mat3 Vrk = mat3(t2.x,t2.y,t2.z,  t2.y,t3.x,t3.y,  t2.z,t3.y,t3.z) * ss;
  float zc = cam.z;
  mat3 J = mat3(uFocal.x/zc, 0.0, -uFocal.x*cam.x/(zc*zc),
                0.0, uFocal.y/zc, -uFocal.y*cam.y/(zc*zc),
                0.0, 0.0, 0.0);
  mat3 W = mat3(uView);
  mat3 Tm = J * W;
  mat3 cov = Tm * Vrk * transpose(Tm);
  float a = cov[0][0] + 0.3, b = cov[0][1], c = cov[1][1] + 0.3;
  float det = a*c - b*b;
  if (det <= 0.0) { gl_Position = vec4(2.0,2.0,2.0,1.0); return; }
  float mid = 0.5*(a+c);
  float rad = sqrt(max(mid*mid - det, 0.0));
  float l1 = mid + rad, l2 = max(mid - rad, 0.1);
  vec2 e1 = normalize(vec2(b, l1 - a));
  vec2 e2 = vec2(e1.y, -e1.x);
  vec2 major = min(3.0*sqrt(l1), 256.0) * e1;
  vec2 minor = min(3.0*sqrt(l2), 256.0) * e2;
  vColor = color;
  vOpacity = opacity * mix(0.62, 1.0, e);
  vQuad = aCorner;
  vec2 ndc = clip.xy / clip.w;
  vec2 offset = (aCorner.x*major + aCorner.y*minor) * 2.0 / uViewport;
  gl_Position = vec4(ndc + offset, clip.z/clip.w, 1.0);
}`;

const FRAG = `#version 300 es
precision highp float;
in vec3 vColor; in float vOpacity; in vec2 vQuad; out vec4 frag;
void main(){
  float r2 = dot(vQuad, vQuad);
  if (r2 > 1.0) discard;
  float alpha = vOpacity * exp(-4.5 * r2);
  if (alpha < 0.004) discard;
  frag = vec4(vColor * alpha, alpha);
}`;

const ANIM: Record<string, number> = { none: 0, breathe: 1, sway: 2, bounce: 3, float: 4,
  jelly: 5, wave: 6, spin: 7, walk: 8, handwave: 9, flow: 10, rig: 11, water: 12, soil: 13 };

function halfToFloat(h: number) {
  const s = h & 0x8000 ? -1 : 1, e = (h >> 10) & 0x1f, f = h & 0x03ff;
  if (e === 0) return s * Math.pow(2, -14) * (f / 1024);
  if (e === 31) return f ? NaN : s * Infinity;
  return s * Math.pow(2, e - 15) * (1 + f / 1024);
}

const SplatraField = forwardRef<SplatraHandle, { className?: string }>(function SplatraField(
  { className }, apiRef,
) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const engineRef = useRef<{ animate: (s: string) => void; gesture: (n: string) => void;
                             reload: () => void; disassemble: () => void } | null>(null);

  useImperativeHandle(apiRef, () => ({
    animate: (s) => engineRef.current?.animate(s),
    gesture: (n) => engineRef.current?.gesture(n),
    reload: () => engineRef.current?.reload(),
    disassemble: () => engineRef.current?.disassemble(),
  }));

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) { console.error("[SplatraField] no canvas"); return; }
    const gl = canvas.getContext("webgl2", { antialias: false, alpha: true });
    if (!gl) { console.error("[SplatraField] webgl2 unavailable"); return; }
    console.log("[SplatraField] engine init");

    // ---- program ----------------------------------------------------------
    const compile = (t: number, s: string) => {
      const sh = gl.createShader(t)!;
      gl.shaderSource(sh, s); gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
        const info = gl.getShaderInfoLog(sh);
        console.error("[SplatraField] shader compile failed",
          { type: t === gl.VERTEX_SHADER ? "vert" : "frag", info,
            contextLost: gl.isContextLost() });
        throw new Error(info || "shader");
      }
      return sh;
    };
    const prog = gl.createProgram()!;
    gl.attachShader(prog, compile(gl.VERTEX_SHADER, VERT));
    gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog) || "link");
    gl.useProgram(prog);
    const U: Record<string, WebGLUniformLocation | null> = {};
    ["uData","uTexW","uProj","uView","uFocal","uViewport","uT","uSizeScale","uModelScale","uModelCenter","uSwirl",
     "uAnimMode","uAnimT","uAnimAmp","uNJ","uJPos","uJOut","uJReach","uJRot","uJTrans",
     "uNEye","uEyes","uBlink","uFloorY"].forEach((u) => (U[u] = gl.getUniformLocation(prog, u)));

    const vao = gl.createVertexArray(); gl.bindVertexArray(vao);
    const cornerBuf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, cornerBuf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    const idxBuf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, idxBuf);
    gl.enableVertexAttribArray(1); gl.vertexAttribIPointer(1, 1, gl.UNSIGNED_INT, 0, 0);
    gl.vertexAttribDivisor(1, 1);
    const dataTex = gl.createTexture();

    // ---- state -------------------------------------------------------------
    const TEXW = 2048;
    let COUNT = 0, homePos: Float32Array | null = null;
    let modelCenter = [0, 0, 0], modelFit = 1;   // per-model normalize (any generator output frames the same)
    let order = new Uint32Array(0), depths = new Float32Array(0);
    const counts = new Uint32Array(65536);
    let lastSortKey = "";
    let yaw = 0.7, pitch = 0.4, dist = 3.4; const target = [0, 0, 0];
    let swirl = 0, modelFloorY = -1, budget = 120000, loading = false;
    const anim = { t: 1, mode: "idle" as string, from: 1, to: 1, t0: 0, dur: 1400, next: null as string | null };
    const av = { mode: 10, amp: 0, target: 1, speed: 2.4 };
    const sw = { active: false, f: 0, t: 0, t0: 0, dur: 800 };
    const cam = { active: false, fy: 0, fp: 0, fd: 0, ty: 0, tp: 0, td: 0, t0: 0, dur: 1200 };
    const MOOD = { amp: 0.35, tempo: 0.8, jitter: 0.05, droop: 0.0 };
    const gestureState = { chain: [] as number[], until: 0 };
    let lrig: any = null, parts: any = null, blink = 0, baseDist: number | null = null;
    const jDrives = new Float32Array(16), jRot = new Float32Array(144), jTrans = new Float32Array(48);
    const eyeVec = new Float32Array(16);

    const tween = (to: number, dur = 1400, next: string | null = null) => {
      anim.mode = "tween"; anim.from = anim.t; anim.to = to; anim.t0 = performance.now(); anim.dur = dur; anim.next = next;
    };
    const swirlTo = (t: number, dur = 800) => { sw.active = true; sw.f = swirl; sw.t = t; sw.t0 = performance.now(); sw.dur = dur; };
    const camTo = (y: number, p: number, d: number, dur = 1200) => {
      cam.active = true; cam.fy = yaw; cam.fp = pitch; cam.fd = dist; cam.ty = y; cam.tp = p; cam.td = d; cam.t0 = performance.now(); cam.dur = dur;
    };

    // ---- math ---------------------------------------------------------------
    const perspective = (fovy: number, aspect: number, near: number, far: number) => {
      const f = 1 / Math.tan(fovy / 2), nf = 1 / (near - far);
      return [f/aspect,0,0,0, 0,f,0,0, 0,0,(far+near)*nf,-1, 0,0,2*far*near*nf,0];
    };
    const sub = (a: number[], b: number[]) => [a[0]-b[0], a[1]-b[1], a[2]-b[2]];
    const dot = (a: number[], b: number[]) => a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
    const cross = (a: number[], b: number[]) => [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
    const norm = (a: number[]) => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0]/l, a[1]/l, a[2]/l]; };
    const lookAt = (eye: number[], ctr: number[], up: number[]) => {
      const z = norm(sub(eye, ctr)), x = norm(cross(up, z)), y = cross(z, x);
      return [x[0],y[0],z[0],0, x[1],y[1],z[1],0, x[2],y[2],z[2],0, -dot(x,eye),-dot(y,eye),-dot(z,eye),1];
    };

    // ---- FK (mirror of rigging/live_rig.pose_chain) -------------------------
    const m3axis = (ax: number, ay: number, az: number, a: number) => {
      const c = Math.cos(a), s = Math.sin(a), t = 1 - c;
      return [t*ax*ax+c, t*ax*ay-s*az, t*ax*az+s*ay, t*ax*ay+s*az, t*ay*ay+c, t*ay*az-s*ax,
              t*ax*az-s*ay, t*ay*az+s*ax, t*az*az+c];
    };
    const m3mul = (A: number[], B: number[]) => {
      const R = new Array(9);
      for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++)
        R[r*3+c] = A[r*3]*B[c] + A[r*3+1]*B[3+c] + A[r*3+2]*B[6+c];
      return R;
    };
    const m3v = (A: number[], v: number[]) => [
      A[0]*v[0]+A[1]*v[1]+A[2]*v[2], A[3]*v[0]+A[4]*v[1]+A[5]*v[2], A[6]*v[0]+A[7]*v[1]+A[8]*v[2]];
    const I9 = [1,0,0,0,1,0,0,0,1];
    function computeFK(t: number) {
      for (let k = 0; k < 16; k++) { jRot.set(I9, k*9); jTrans.set([0,0,0], k*3); }
      if (!lrig) return;
      // 견고한 몸: idle sway is scaled by how far a joint sits from the body
      // centre — core joints barely move (the clock face stays RIGID), only
      // limb tips carry the life. A gesture overrides one chain, full drive.
      const dmax = Math.max(...lrig.joints.map((j: number[]) =>
        Math.hypot(j[0]-lrig.centroid[0], j[1]-lrig.centroid[1], j[2]-lrig.centroid[2]))) || 1;
      const g = gestureState.until > performance.now() ? gestureState : null;
      for (let k = 0; k < lrig.n; k++) {
        const j = lrig.joints[k];
        const dn = Math.hypot(j[0]-lrig.centroid[0], j[1]-lrig.centroid[1], j[2]-lrig.centroid[2]) / dmax;
        const s = Math.min(1, Math.max(0, (dn - 0.35) / 0.4));
        const distal = 0.06 + 0.94 * s * s * (3 - 2 * s);
        if (g && g.chain.includes(k)) {
          jDrives[k] = 1.05 * Math.sin(5.2*t + k*0.8);           // the wave
        } else if (g) {
          jDrives[k] = 0;                                        // rest holds still
        } else {
          jDrives[k] = distal * (MOOD.amp*Math.sin(MOOD.tempo*t + k*1.7)
            + MOOD.jitter*0.3*Math.sin(7.3*t + k*2.9)) - MOOD.droop*0.35*distal;
        }
      }
      for (const chain of (lrig.chains || [])) {
        const Jw = chain.map((j: number) => lrig.joints[j].slice());
        let prev = lrig.centroid.slice();
        let R = I9.slice(), T = [0, 0, 0];
        for (let c = 0; c < chain.length; c++) {
          const j = chain[c]; if (j >= 16) continue;
          let d = [Jw[c][0]-prev[0], Jw[c][1]-prev[1], Jw[c][2]-prev[2]];
          let n = Math.hypot(d[0], d[1], d[2]);
          d = n > 1e-5 ? d.map((x: number) => x/n) : [lrig.out[j*3], lrig.out[j*3+1], lrig.out[j*3+2]];
          let ax = [d[2], 0, -d[0]]; n = Math.hypot(ax[0], ax[1], ax[2]);
          ax = n > 1e-4 ? ax.map((x) => x/n) : [1, 0, 0];
          const Rk = m3axis(ax[0], ax[1], ax[2], jDrives[j]);
          const piv = Jw[c];
          const Rn = m3mul(Rk, R);
          const Tk = m3v(Rk, [T[0]-piv[0], T[1]-piv[1], T[2]-piv[2]]);
          R = Rn; T = [Tk[0]+piv[0], Tk[1]+piv[1], Tk[2]+piv[2]];
          jRot.set(R, j*9); jTrans.set(T, j*3);
          for (let m = c + 1; m < chain.length; m++) {
            const v = m3v(Rk, [Jw[m][0]-piv[0], Jw[m][1]-piv[1], Jw[m][2]-piv[2]]);
            Jw[m] = [v[0]+piv[0], v[1]+piv[1], v[2]+piv[2]];
          }
          prev = Jw[c];
        }
      }
    }

    // ---- server: rig / parts / mood ----------------------------------------
    async function fetchRig() {
      try {
        const r = await fetch(`${API}/v1/rig`); if (!r.ok) { lrig = null; return; }
        const d = await r.json();
        const flat = (k: string) => { const a = new Float32Array(48); d[k].forEach((v: number[], i: number) => a.set(v, i*3)); return a; };
        lrig = { n: Math.min(d.n_joints, 16), pos: flat("joints"), out: flat("outward"),
                 joints: d.joints, chains: d.chains, centroid: d.centroid, reach: d.reach, avatar: !!d.avatar };
      } catch { lrig = null; }
      fetchParts();
    }
    async function fetchParts() {
      try {
        const r = await fetch(`${API}/v1/parts`); if (!r.ok) { parts = null; return; }
        const d = await r.json();
        parts = { eyes: (d.eyes || []).slice(0, 4) };
        eyeVec.fill(0);
        parts.eyes.forEach((e: any, i: number) => eyeVec.set([e.center[0], e.center[1], e.center[2], e.radius], i*4));
      } catch { parts = null; }
    }
    async function pollMood() {
      if (!lrig || !lrig.avatar) return;      // 감정은 기계 자신의 캐릭터에만
      try {
        const r = await fetch(`${API}/v1/rig_mood`, { method: "POST",
          headers: { "Content-Type": "application/json" }, body: JSON.stringify({ dry: true }) });
        if (!r.ok) return;
        const p = (await r.json()).params;
        MOOD.amp = p.amp; MOOD.tempo = p.tempo; MOOD.jitter = p.jitter; MOOD.droop = p.droop;
      } catch { /* engine offline */ }
    }
    const moodTimer = setInterval(() => { if (av.mode === 11) pollMood(); }, 5000);

    // ---- upload / sort ------------------------------------------------------
    function uploadModel(pos: Float32Array, col: Float32Array, scale: Float32Array, quat: Float32Array, opa: Float32Array) {
      const n = opa.length;
      modelFloorY = Infinity;
      for (let i = 0; i < n; i++) if (pos[3*i+1] < modelFloorY) modelFloorY = pos[3*i+1];
      if (!isFinite(modelFloorY)) modelFloorY = -1;
      // Fit-normalize: the owner's pikachu filled the whole screen because the
      // generator's coordinate scale is arbitrary. Center on the centroid and
      // scale a ROBUST radius (mean-capped, so one stray splat can't shrink
      // the body) to a fixed framed size — every model, same stage.
      let cx = 0, cy = 0, cz = 0;
      for (let i = 0; i < n; i++) { cx += pos[3*i]; cy += pos[3*i+1]; cz += pos[3*i+2]; }
      const inv = 1 / (n || 1);
      cx *= inv; cy *= inv; cz *= inv;
      let rsum = 0, rmax = 0;
      for (let i = 0; i < n; i++) {
        const dx = pos[3*i]-cx, dy = pos[3*i+1]-cy, dz = pos[3*i+2]-cz;
        const r = Math.sqrt(dx*dx + dy*dy + dz*dz);
        rsum += r; if (r > rmax) rmax = r;
      }
      const rFit = Math.min(rmax, (rsum * inv) * 2.6) || 1;
      modelCenter = [cx, cy, cz];
      modelFit = 1.15 / Math.max(0.2, rFit);
      const texH = Math.ceil(n*4 / TEXW);
      const tex = new Float32Array(TEXW * texH * 4);
      for (let i = 0; i < n; i++) {
        let w = quat[4*i], x = quat[4*i+1], y = quat[4*i+2], z = quat[4*i+3];
        const ql = Math.hypot(w, x, y, z) || 1; w /= ql; x /= ql; y /= ql; z /= ql;
        const sx = scale[3*i], sy = scale[3*i+1], sz = scale[3*i+2];
        const r00 = 1-2*(y*y+z*z), r01 = 2*(x*y-w*z), r02 = 2*(x*z+w*y);
        const r10 = 2*(x*y+w*z), r11 = 1-2*(x*x+z*z), r12 = 2*(y*z-w*x);
        const r20 = 2*(x*z-w*y), r21 = 2*(y*z+w*x), r22 = 1-2*(x*x+y*y);
        const sx2 = sx*sx, sy2 = sy*sy, sz2 = sz*sz;
        const o = i * 16;
        tex[o] = pos[3*i]; tex[o+1] = pos[3*i+1]; tex[o+2] = pos[3*i+2]; tex[o+3] = opa[i];
        tex[o+4] = col[3*i]; tex[o+5] = col[3*i+1]; tex[o+6] = col[3*i+2];
        tex[o+8] = r00*r00*sx2 + r01*r01*sy2 + r02*r02*sz2;
        tex[o+9] = r00*r10*sx2 + r01*r11*sy2 + r02*r12*sz2;
        tex[o+10] = r00*r20*sx2 + r01*r21*sy2 + r02*r22*sz2;
        tex[o+12] = r10*r10*sx2 + r11*r11*sy2 + r12*r12*sz2;
        tex[o+13] = r10*r20*sx2 + r11*r21*sy2 + r12*r22*sz2;
        tex[o+14] = r20*r20*sx2 + r21*r21*sy2 + r22*r22*sz2;
      }
      gl.bindTexture(gl.TEXTURE_2D, dataTex);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA32F, TEXW, texH, 0, gl.RGBA, gl.FLOAT, tex);
      homePos = pos; COUNT = n;
      order = new Uint32Array(n); for (let i = 0; i < n; i++) order[i] = i;
      depths = new Float32Array(n);
      lastSortKey = "";
    }

    function sortSplats(view: number[]) {
      if (!COUNT || !homePos) return;
      const m2 = view[2], m6 = view[6], m10 = view[10], m14 = view[14];
      let zmin = 1e30, zmax = -1e30;
      for (let i = 0; i < COUNT; i++) {
        const d = m2*homePos[3*i] + m6*homePos[3*i+1] + m10*homePos[3*i+2] + m14;
        depths[i] = d; if (d < zmin) zmin = d; if (d > zmax) zmax = d;
      }
      const scale = 65535 / ((zmax - zmin) || 1);
      counts.fill(0);
      for (let i = 0; i < COUNT; i++) counts[((depths[i]-zmin)*scale) | 0]++;
      for (let k = 1; k < 65536; k++) counts[k] += counts[k-1];
      for (let i = COUNT - 1; i >= 0; i--) { const key = ((depths[i]-zmin)*scale) | 0; order[--counts[key]] = i; }
      gl.bindBuffer(gl.ARRAY_BUFFER, idxBuf);
      gl.bufferData(gl.ARRAY_BUFFER, order, gl.DYNAMIC_DRAW);
    }

    // ---- cartridge ----------------------------------------------------------
    function parseSPL2(b: ArrayBuffer, dv: DataView) {
      const n = dv.getUint32(4, true); let o = 8;
      const pos = new Float32Array(b, o, n*3); o += n*12;
      const col = new Float32Array(b, o, n*3); o += n*12;
      const scale = new Float32Array(b, o, n*3); o += n*12;
      const quat = new Float32Array(b, o, n*4); o += n*16;
      const opa = new Float32Array(b, o, n);
      return { pos, col, scale, quat, opa };
    }
    function parseSPL3(b: ArrayBuffer, dv: DataView) {
      const n = dv.getUint32(4, true);
      const mn = [dv.getFloat32(8, true), dv.getFloat32(12, true), dv.getFloat32(16, true)];
      const mx = [dv.getFloat32(20, true), dv.getFloat32(24, true), dv.getFloat32(28, true)];
      const span = [Math.max(1e-8, mx[0]-mn[0]), Math.max(1e-8, mx[1]-mn[1]), Math.max(1e-8, mx[2]-mn[2])];
      let o = 32;
      const pos = new Float32Array(n*3);
      for (let i = 0; i < n*3; i++) { const ax = i % 3; const q = dv.getInt16(o, true); o += 2;
        pos[i] = mn[ax] + ((q + 32768) / 65535) * span[ax]; }
      const col = new Float32Array(n*3);
      for (let i = 0; i < n*3; i++) col[i] = dv.getUint8(o++) / 255;
      const scale = new Float32Array(n*3);
      for (let i = 0; i < n*3; i++) { scale[i] = halfToFloat(dv.getUint16(o, true)); o += 2; }
      const quat = new Float32Array(n*4);
      for (let i = 0; i < n*4; i++) quat[i] = Math.max(-1, dv.getInt8(o++) / 127);
      const opa = new Float32Array(n);
      for (let i = 0; i < n; i++) opa[i] = dv.getUint8(o++) / 255;
      return { pos, col, scale, quat, opa };
    }
    async function loadCartridge(animateIn = true) {
      if (loading) return;
      loading = true;
      try {
        const u = `${API}/v1/cartridge?format=spl3&budget=${budget}&_=${Date.now()}`;
        const res = await fetch(u); if (!res.ok) return;
        const b = await res.arrayBuffer();
        const dv = new DataView(b);
        const magic = String.fromCharCode(dv.getUint8(0), dv.getUint8(1), dv.getUint8(2), dv.getUint8(3));
        if (magic !== "SPL2" && magic !== "SPL3") return;
        const { pos, col, scale, quat, opa } = magic === "SPL3" ? parseSPL3(b, dv) : parseSPL2(b, dv);
        uploadModel(pos, col, scale, quat, opa);
        if (animateIn) { anim.t = 0; tween(1, 1700);
          const aligned = Math.abs(swirl/(2*Math.PI) - Math.round(swirl/(2*Math.PI))) < 0.02;
          swirlTo(aligned ? swirl : Math.ceil(swirl/(2*Math.PI) - 1e-6) * 2*Math.PI, 1700);
          // normalized model sits at the origin — re-center and frame it so the
          // camera can never start inside the body (the giant-pink-blur bug)
          target[0] = 0; target[1] = 0; target[2] = 0;
          camTo(yaw, pitch, baseDist != null ? baseDist : 3.4, 1700); baseDist = null; }
        fetchRig();
      } finally { loading = false; }
    }
    function disassemble() {
      if (COUNT) { baseDist = dist; camTo(yaw, pitch, Math.min(dist*1.35, 8.5), 800);
        swirlTo(swirl + Math.PI, 800); tween(0, 800, "scatter"); }
    }

    engineRef.current = {
      animate: (style: string) => {
        // 아토 불변 계약: the machine's own character never melts or crumbles —
        // material morphs are for demonstration OBJECTS only
        if ((style === "water" || style === "soil") && lrig?.avatar) return;
        const m = ANIM[style] ?? (style === "stop" || style === "none" ? 0 : av.mode);
        if (m) { av.mode = m; av.target = 1;
          av.speed = style === "spin" ? 1.0 : style === "walk" ? 6.0 : 2.4; }
        else { av.target = 0; }
      },
      gesture: (name: string) => {
        // move ONE limb on the EXISTING body — never regenerate for a greeting
        if (!lrig || !lrig.chains?.length) return;
        av.mode = 11; av.target = 1;
        if (name === "wave") {
          // the arm = chain reaching farthest sideways
          let best = lrig.chains[0], score = -1;
          for (const ch of lrig.chains) {
            const sx = Math.max(...ch.map((j: number) => Math.abs(lrig.joints[j][0])));
            if (sx > score) { score = sx; best = ch; }
          }
          gestureState.chain = best;
          gestureState.until = performance.now() + 3200;
        }
      },
      reload: () => { disassemble(); setTimeout(() => loadCartridge(true).catch(() => {}), 520); },
      disassemble,
    };

    // ---- input --------------------------------------------------------------
    let drag: { x: number; y: number; pan: boolean } | null = null;
    const onDown = (e: MouseEvent) => { drag = { x: e.clientX, y: e.clientY, pan: e.button === 2 || e.shiftKey }; };
    const onUp = () => { drag = null; };
    const onMove = (e: MouseEvent) => {
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.x = e.clientX; drag.y = e.clientY;
      if (drag.pan) { const r = norm(cross([0,1,0], [Math.sin(yaw), 0, Math.cos(yaw)])); const k = dist*0.0016;
        target[0] -= r[0]*dx*k; target[2] -= r[2]*dx*k; target[1] += dy*k; }
      else { yaw += dx*0.01; pitch = Math.max(-1.45, Math.min(1.45, pitch - dy*0.01)); }
    };
    const onWheel = (e: WheelEvent) => { e.preventDefault(); dist = Math.max(1.3, Math.min(9, dist*(1 + e.deltaY*0.0012))); };
    const onCtx = (e: Event) => e.preventDefault();
    canvas.addEventListener("mousedown", onDown);
    window.addEventListener("mouseup", onUp);
    window.addEventListener("mousemove", onMove);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("contextmenu", onCtx);

    // ---- render loop --------------------------------------------------------
    let dead = false;
    function frame() {
      if (dead) return;
      const now = performance.now();
      if (anim.mode === "tween") { const k = Math.min(1, (now - anim.t0)/anim.dur);
        anim.t = anim.from + (anim.to - anim.from)*k;
        if (k >= 1) { anim.mode = anim.next || "idle"; anim.next = null; } }
      else if (anim.mode === "scatter") { anim.t = 0.10 + 0.05*Math.sin(now*0.0016); swirl += 0.004; }
      if (cam.active) { const k = Math.min(1, (now - cam.t0)/cam.dur), e = k*k*(3-2*k);
        yaw = cam.fy + (cam.ty - cam.fy)*e; pitch = cam.fp + (cam.tp - cam.fp)*e; dist = cam.fd + (cam.td - cam.fd)*e;
        if (k >= 1) cam.active = false; }
      if (sw.active) { const k = Math.min(1, (now - sw.t0)/sw.dur), e = k*k*(3-2*k);
        swirl = sw.f + (sw.t - sw.f)*e; if (k >= 1) sw.active = false; }

      const dpr = Math.min(devicePixelRatio || 1, 2);
      const w = (canvas.clientWidth*dpr) | 0 || 800, h = (canvas.clientHeight*dpr) | 0 || 600;
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
      gl.viewport(0, 0, w, h);
      gl.clearColor(0, 0, 0, 0);                 // 대시보드 배경 위에 그대로 합성
      gl.clear(gl.COLOR_BUFFER_BIT);
      if (COUNT) {
        const eye = [target[0] + dist*Math.cos(pitch)*Math.sin(yaw),
                     target[1] + dist*Math.sin(pitch),
                     target[2] + dist*Math.cos(pitch)*Math.cos(yaw)];
        const proj = perspective(50*Math.PI/180, w/h, 0.05, 100), view = lookAt(eye, target, [0, 1, 0]);
        const key = `${yaw.toFixed(3)},${pitch.toFixed(3)},${dist.toFixed(2)},${target.map((v) => v.toFixed(2))}`;
        if (key !== lastSortKey || anim.mode !== "idle") { sortSplats(view); lastSortKey = key; }
        gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA); gl.disable(gl.DEPTH_TEST);
        gl.useProgram(prog); gl.bindVertexArray(vao);
        gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, dataTex);
        gl.uniform1i(U.uData, 0); gl.uniform1i(U.uTexW, TEXW);
        gl.uniformMatrix4fv(U.uProj, false, proj); gl.uniformMatrix4fv(U.uView, false, view);
        gl.uniform2f(U.uFocal, proj[0]*0.5*w, proj[5]*0.5*h);
        gl.uniform2f(U.uViewport, w, h);
        gl.uniform1f(U.uT, anim.t); gl.uniform1f(U.uSizeScale, modelFit);
        gl.uniform1f(U.uModelScale, modelFit); gl.uniform1f(U.uSwirl, swirl);
        gl.uniform3f(U.uModelCenter, modelCenter[0], modelCenter[1], modelCenter[2]);
        av.amp += (av.target - av.amp)*0.06;
        if (av.amp < 0.004 && av.target === 0) av.mode = 0;
        gl.uniform1i(U.uAnimMode, av.mode); gl.uniform1f(U.uAnimT, now*0.001*av.speed); gl.uniform1f(U.uAnimAmp, av.amp);
        if (av.mode === 11 && lrig) {
          computeFK(now*0.001);
          gl.uniform1i(U.uNJ, lrig.n); gl.uniform3fv(U.uJPos, lrig.pos);
          gl.uniform3fv(U.uJOut, lrig.out); gl.uniform1f(U.uJReach, lrig.reach);
          gl.uniformMatrix3fv(U.uJRot, true, jRot); gl.uniform3fv(U.uJTrans, jTrans);
        } else gl.uniform1i(U.uNJ, 0);
        if (parts && parts.eyes.length) {
          const cyc = (now*0.001) % 4.2;
          blink = cyc < 0.28 ? (cyc/0.14 < 1 ? cyc/0.14 : 2 - cyc/0.14) : 0;
          gl.uniform1i(U.uNEye, parts.eyes.length); gl.uniform4fv(U.uEyes, eyeVec);
          gl.uniform1f(U.uBlink, blink);
        } else { gl.uniform1i(U.uNEye, 0); gl.uniform1f(U.uBlink, 0); }
        gl.uniform1f(U.uFloorY, modelFloorY);
        gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, COUNT);
      }
    }
    // setInterval (not rAF): rAF never fires in a hidden tab, and this field
    // must keep living when the dashboard window is covered or remote-driven
    const loop = setInterval(frame, 16);
    loadCartridge(true).catch(() => {});

    return () => {
      dead = true;
      clearInterval(loop);
      clearInterval(moodTimer);
      canvas.removeEventListener("mousedown", onDown);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("mousemove", onMove);
      canvas.removeEventListener("wheel", onWheel);
      canvas.removeEventListener("contextmenu", onCtx);
      // NOTE: never loseContext() here — React StrictMode double-mounts the
      // effect, and a re-mounted getContext() on the same canvas returns the
      // SAME (now dead) context, silently no-oping every GL call.
      engineRef.current = null;
    };
  }, []);

  return <canvas ref={canvasRef} className={className} style={{ width: "100%", height: "100%", display: "block" }} />;
});

export default SplatraField;
