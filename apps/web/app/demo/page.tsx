"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Brain, CheckCircle2, Cloud, Globe2, Layers3, Lock, MessageCircle, Network, Play, Sparkles, Zap } from "lucide-react";
import styles from "./showcase.module.css";

type StageState = "queued" | "running" | "complete";

const fixedQuestion = "If ATANOR launches as a local-first graph-native AI workstation, which communities adopt it first, and what narrative makes it spread?";

const stages: Array<{ label: string; detail: string; icon: typeof Brain }> = [
  { label: "Seed Ingestion", detail: "launch copy, architecture docs, proof artifacts", icon: Layers3 },
  { label: "Graph Expansion", detail: "1.28B virtual nodes / 9.7B relation candidates", icon: Network },
  { label: "Audience Simulation", detail: "developer, researcher, privacy, and OSS clusters", icon: Brain },
  { label: "Signal Prediction", detail: "adoption waves, objections, bridge narratives", icon: Zap },
  { label: "Report Synthesis", detail: "decision-ready narrative map", icon: CheckCircle2 },
];

const communities = [
  { name: "Local-first builders", share: 34, reason: "They already distrust remote-only memory and want inspectable state." },
  { name: "GraphRAG engineers", share: 27, reason: "Graph cartridges make retrieval structure portable instead of trapped in prompts." },
  { name: "Privacy researchers", share: 18, reason: "The Local Brain / Cloud Brain boundary gives them something concrete to audit." },
  { name: "Indie AI power users", share: 13, reason: "A workstation-native AI system feels ownable, modifiable, and visually legible." },
  { name: "Open-source toolmakers", share: 8, reason: "Proof artifacts and packageable knowledge invite forks and adapters." },
];

const forecastCards = [
  {
    title: "First adoption wave",
    value: "GraphRAG + local-first developers",
    copy: "The strongest first hook is not model quality. It is visible memory: users can see what the system knows, where it came from, and whether it wrote to private memory.",
  },
  {
    title: "Viral narrative",
    value: "Prompt packs are not enough",
    copy: "The shareable line is that knowledge should ship as auditable graph cartridges, not as fragile prompt snippets or opaque fine-tunes.",
  },
  {
    title: "Main objection",
    value: "Is this real or just a pretty graph?",
    copy: "The answer needs proof artifacts, tests, and a clear alpha boundary. Visual spectacle works only when it points to inspectable files.",
  },
  {
    title: "Best launch move",
    value: "Show the memory surface",
    copy: "A fixed demo question, billion-node visualization, and generated report should make ATANOR feel like a new substrate rather than another chat UI.",
  },
];

function formatCount(value: number) {
  return new Intl.NumberFormat("en-US").format(Math.round(value));
}

function stageState(index: number, progress: number): StageState {
  const threshold = (index + 1) / stages.length;
  const previous = index / stages.length;
  if (progress >= threshold) return "complete";
  if (progress >= previous) return "running";
  return "queued";
}

function useDemoProgress() {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    let frame = 0;
    let start = 0;
    const tick = (time: number) => {
      if (!start) start = time;
      const elapsed = time - start;
      const loop = (elapsed % 18000) / 18000;
      const eased = loop < 0.88 ? loop / 0.88 : 1;
      setProgress(eased);
      frame = window.requestAnimationFrame(tick);
    };
    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, []);

  return progress;
}

function BillionNodeField({ progress }: { progress: number }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const host = canvas?.parentElement;
    if (!canvas || !host) return undefined;

    const context = canvas.getContext("2d", { alpha: true });
    if (!context) return undefined;

    let frame = 0;
    const pixelRatio = Math.min(window.devicePixelRatio || 1, 1.6);
    const points = Array.from({ length: 760 }, (_, index) => {
      const ring = index % 17;
      const angle = index * 2.399963 + ring * 0.13;
      const radius = 0.08 + Math.pow((index % 113) / 113, 0.72) * 0.86;
      return {
        angle,
        radius,
        size: 0.45 + (index % 9) * 0.11,
        tone: index % 11 === 0 ? "hot" : index % 5 === 0 ? "cloud" : "node",
      };
    });

    const resize = () => {
      const rect = host.getBoundingClientRect();
      canvas.width = Math.max(1, Math.floor(rect.width * pixelRatio));
      canvas.height = Math.max(1, Math.floor(rect.height * pixelRatio));
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;
      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    };

    const draw = (time: number) => {
      const rect = host.getBoundingClientRect();
      const width = rect.width;
      const height = rect.height;
      const centerX = width * 0.5;
      const centerY = height * 0.52;
      const radiusBase = Math.min(width, height) * 0.43;

      context.clearRect(0, 0, width, height);
      context.fillStyle = "#020409";
      context.fillRect(0, 0, width, height);

      const glow = context.createRadialGradient(centerX, centerY, radiusBase * 0.08, centerX, centerY, radiusBase * 1.16);
      glow.addColorStop(0, "rgba(255, 145, 56, 0.2)");
      glow.addColorStop(0.35, "rgba(53, 122, 190, 0.16)");
      glow.addColorStop(1, "rgba(0, 0, 0, 0)");
      context.fillStyle = glow;
      context.fillRect(0, 0, width, height);

      context.save();
      context.translate(centerX, centerY);
      context.rotate(time / 42000);

      for (let ring = 0; ring < 9; ring += 1) {
        context.beginPath();
        context.ellipse(0, 0, radiusBase * (0.22 + ring * 0.085), radiusBase * (0.08 + ring * 0.035), ring * 0.31, 0, Math.PI * 2);
        context.strokeStyle = `rgba(255, 255, 255, ${0.035 + ring * 0.004})`;
        context.lineWidth = 1;
        context.stroke();
      }

      points.forEach((point, index) => {
        const wave = Math.sin(time / 1400 + index * 0.19) * 0.026;
        const radius = radiusBase * (point.radius + wave);
        const angle = point.angle + time / (point.tone === "hot" ? 8200 : 15000);
        const squash = 0.46 + Math.sin(point.angle) * 0.04;
        const x = Math.cos(angle) * radius;
        const y = Math.sin(angle) * radius * squash;
        const isVisible = (index / points.length) < Math.max(0.16, progress);
        const alpha = isVisible ? 0.34 + progress * 0.42 : 0.07;

        context.beginPath();
        context.arc(x, y, point.size * (point.tone === "hot" ? 2.2 : 1.15), 0, Math.PI * 2);
        context.fillStyle = point.tone === "hot"
          ? `rgba(255, 159, 28, ${alpha})`
          : point.tone === "cloud"
            ? `rgba(87, 151, 232, ${alpha * 0.9})`
            : `rgba(211, 236, 231, ${alpha * 0.72})`;
        context.fill();

        if (index % 37 === 0) {
          context.beginPath();
          context.moveTo(x, y);
          context.lineTo(Math.cos(angle + 0.54) * radius * 0.72, Math.sin(angle + 0.54) * radius * 0.72 * squash);
          context.strokeStyle = `rgba(255, 159, 28, ${alpha * 0.18})`;
          context.stroke();
        }
      });

      context.restore();
      frame = window.requestAnimationFrame(draw);
    };

    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    frame = window.requestAnimationFrame(draw);
    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [progress]);

  return <canvas ref={canvasRef} className={styles.nodeCanvas} aria-label="Synthetic billion-node ATANOR graph visualization" />;
}

export default function AtanorShowcaseDemo() {
  const progress = useDemoProgress();
  const virtualNodes = useMemo(() => 180_000_000 + progress * 1_100_000_000, [progress]);
  const virtualEdges = useMemo(() => 1_200_000_000 + progress * 8_500_000_000, [progress]);
  const confidence = Math.min(91, 42 + progress * 56);
  const completedStages = stages.filter((_, index) => stageState(index, progress) === "complete").length;

  return (
    <main className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <span>ATANOR</span>
          <strong>Mock Prediction Demo</strong>
        </div>
        <nav className={styles.nav} aria-label="Demo sections">
          <a href="#simulation"><Globe2 size={18} /> Simulation</a>
          <a href="#question"><MessageCircle size={18} /> Fixed RAG Query</a>
          <a href="#forecast"><Sparkles size={18} /> Forecast</a>
          <a href="#boundary"><Lock size={18} /> Boundary</a>
        </nav>
        <div className={styles.sideStats}>
          <span><i /> Local Brain</span>
          <strong>PRIVATE</strong>
          <span><i data-blue /> Cloud Brain</span>
          <strong>MOCK RELAY</strong>
        </div>
      </aside>

      <section className={styles.main}>
        <header className={styles.topbar}>
          <div>
            <span>PUBLIC SHOWCASE / SYNTHETIC DATA</span>
            <h1>Predict the launch before it happens.</h1>
          </div>
          <button type="button"><Play size={16} /> Auto-running demo</button>
        </header>

        <section className={styles.hero} id="simulation">
          <div className={styles.graphStage}>
            <BillionNodeField progress={progress} />
            <div className={styles.stageOverlay}>
              <span>Virtualized Knowledge Surface</span>
              <strong>{formatCount(virtualNodes)} nodes</strong>
              <small>{formatCount(virtualEdges)} relation candidates</small>
            </div>
            <div className={styles.scaleBadge}>
              <span>Rendered sample</span>
              <strong>760 visible points</strong>
              <small>representing billion-scale graph state</small>
            </div>
          </div>

          <aside className={styles.pipeline}>
            <div className={styles.pipelineHeader}>
              <span>ATANOR Prediction Run</span>
              <strong>{Math.round(progress * 100)}%</strong>
            </div>
            <div className={styles.progressTrack}><i style={{ width: `${progress * 100}%` }} /></div>
            {stages.map((stage, index) => {
              const Icon = stage.icon;
              const state = stageState(index, progress);
              return (
                <article key={stage.label} className={styles.stageRow} data-state={state}>
                  <Icon size={18} />
                  <div>
                    <strong>{stage.label}</strong>
                    <span>{stage.detail}</span>
                  </div>
                </article>
              );
            })}
            <div className={styles.metricGrid}>
              <span><small>Completed stages</small><strong>{completedStages}/5</strong></span>
              <span><small>Confidence</small><strong>{Math.round(confidence)}%</strong></span>
              <span><small>Private memory</small><strong>not shared</strong></span>
              <span><small>Mode</small><strong>mock</strong></span>
            </div>
          </aside>
        </section>

        <section className={styles.questionPanel} id="question">
          <div className={styles.chatHeader}>
            <MessageCircle size={20} />
            <div>
              <span>Fixed RAG Chat Prompt</span>
              <strong>Question is locked for the showcase.</strong>
            </div>
          </div>
          <div className={styles.chatBubble} data-role="user">{fixedQuestion}</div>
          <div className={styles.chatBubble} data-role="assistant">
            <strong>Prediction:</strong> ATANOR spreads first through builders who already feel the pain of opaque memory. The winning story is not "another AI chat app"; it is "a visible memory architecture you can own, inspect, and repair."
          </div>
        </section>

        <section className={styles.forecastGrid} id="forecast">
          {forecastCards.map((card) => (
            <article key={card.title}>
              <span>{card.title}</span>
              <h2>{card.value}</h2>
              <p>{card.copy}</p>
            </article>
          ))}
        </section>

        <section className={styles.communityPanel}>
          <header>
            <span>Predicted Adoption Clusters</span>
            <strong>Mock audience graph output</strong>
          </header>
          <div className={styles.communityRows}>
            {communities.map((community) => (
              <article key={community.name}>
                <div>
                  <strong>{community.name}</strong>
                  <span>{community.reason}</span>
                </div>
                <i style={{ width: `${community.share}%` }} />
                <em>{community.share}%</em>
              </article>
            ))}
          </div>
        </section>

        <footer className={styles.boundary} id="boundary">
          <Lock size={18} />
          <p>
            This page is a synthetic public demo. It does not call the live ATANOR API, does not process private data,
            and does not claim real billion-node inference. It visualizes the product story and expected workflow.
          </p>
        </footer>
      </section>
    </main>
  );
}
