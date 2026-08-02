"use client";

import { useEffect, useRef } from "react";

type SeismographChartProps = {
  /** Latest live value. Sampled every `tickMs` into a scrolling buffer. */
  value: number;
  /** Fixed top of the scale. Omit for an auto-ranging (smoothed) scale. */
  max?: number;
  /** Trace colour (hex). */
  color?: string;
  /** Number of samples held in the rolling window. */
  samples?: number;
  /** Milliseconds between samples (smaller = faster scroll). */
  tickMs?: number;
  /** When false the trace flatlines at the current value (paused feel). */
  active?: boolean;
  /** Draw the scrolling grid. */
  grid?: boolean;
};

/**
 * Task-Manager–style seismograph: new samples enter at the RIGHT edge and the
 * whole trace scrolls continuously to the LEFT, over a fine grid that scrolls
 * with the data. Canvas + rAF for smooth sub-cell motion.
 */
export default function SeismographChart({
  value,
  max,
  color = "#ff7a1a",
  samples = 160,
  tickMs = 600,
  active = true,
  grid = true,
}: SeismographChartProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const valueRef = useRef(value);
  valueRef.current = Number.isFinite(value) ? value : 0;
  const activeRef = useRef(active);
  activeRef.current = active;
  const bufRef = useRef<number[]>([]);
  const maxRef = useRef<number>(max ?? 1);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    if (bufRef.current.length !== samples) {
      const seed = valueRef.current;
      bufRef.current = Array.from({ length: samples }, () => seed);
    }

    const rgba = (hex: string, a: number) => {
      const h = hex.replace("#", "");
      const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
      const n = parseInt(full, 16);
      return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
    };

    let raf = 0;
    let lastSample = performance.now();
    let gridPx = 0;

    const draw = (now: number) => {
      const dpr = window.devicePixelRatio || 1;
      const cssW = canvas.clientWidth || 320;
      const cssH = canvas.clientHeight || 120;
      if (canvas.width !== Math.round(cssW * dpr) || canvas.height !== Math.round(cssH * dpr)) {
        canvas.width = Math.round(cssW * dpr);
        canvas.height = Math.round(cssH * dpr);
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, cssW, cssH);

      const buf = bufRef.current;
      const N = buf.length;
      const cellW = cssW / (N - 1);

      while (now - lastSample >= tickMs) {
        buf.push(activeRef.current ? valueRef.current : buf[buf.length - 1]);
        if (buf.length > N) buf.shift();
        lastSample += tickMs;
        gridPx += cellW;
      }
      const frac = Math.min(1, (now - lastSample) / tickMs);
      const shift = frac * cellW;

      const peak = Math.max(0.001, ...buf);
      const target = max != null ? max : peak * 1.18;
      maxRef.current += (target - maxRef.current) * 0.07;
      const scaleMax = Math.max(0.001, maxRef.current);

      const top = 9;
      const bottom = cssH - 5;
      const plotH = bottom - top;
      const yOf = (v: number) => bottom - Math.max(0, Math.min(1, v / scaleMax)) * plotH;
      const xOf = (i: number) => i * cellW - shift;

      if (grid) {
        ctx.lineWidth = 1;
        ctx.strokeStyle = "rgba(255,255,255,0.055)";
        for (let r = 0; r <= 4; r++) {
          const y = Math.round(top + (plotH * r) / 4) + 0.5;
          ctx.beginPath();
          ctx.moveTo(0, y);
          ctx.lineTo(cssW, y);
          ctx.stroke();
        }
        const vGap = cellW * 14;
        const off = (gridPx + shift) % vGap;
        for (let x = cssW - off; x > -vGap; x -= vGap) {
          ctx.beginPath();
          ctx.moveTo(x, top);
          ctx.lineTo(x, bottom);
          ctx.stroke();
        }
      }

      // area fill
      ctx.beginPath();
      ctx.moveTo(xOf(0), yOf(buf[0]));
      for (let i = 1; i < N; i++) ctx.lineTo(xOf(i), yOf(buf[i]));
      const grad = ctx.createLinearGradient(0, top, 0, bottom);
      grad.addColorStop(0, rgba(color, 0.36));
      grad.addColorStop(1, rgba(color, 0.02));
      ctx.lineTo(xOf(N - 1), bottom);
      ctx.lineTo(xOf(0), bottom);
      ctx.closePath();
      ctx.fillStyle = grad;
      ctx.fill();

      // line
      ctx.beginPath();
      ctx.moveTo(xOf(0), yOf(buf[0]));
      for (let i = 1; i < N; i++) ctx.lineTo(xOf(i), yOf(buf[i]));
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = color;
      ctx.shadowColor = rgba(color, 0.55);
      ctx.shadowBlur = 7;
      ctx.stroke();
      ctx.shadowBlur = 0;

      // leading dot at the live (right) edge
      ctx.beginPath();
      ctx.arc(xOf(N - 1), yOf(buf[N - 1]), 2.3, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();

      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [samples, tickMs, color, grid, max]);

  return (
    <canvas
      ref={canvasRef}
      className="atanor-seismo"
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%", display: "block" }}
    />
  );
}
