"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { browserMemorySafeMode, chromeHeapSnapshot, graphRenderFpsCap, resolveGraphPixelRatio, shouldRenderGraphFrame, writeGraphTelemetry } from "./graphRendererGuardrails";

type AtlasGlobeNode = {
  key: string;
  lat: number;
  lng: number;
  activity: number;
  source: string;
  state: string;
  role?: string;
};

type AtlasGlobe3DProps = {
  hub: { lat: number; lng: number };
  nodes: AtlasGlobeNode[];
  language: "en" | "ko";
  remoteConnected: boolean;
};

function clampNumber(value: number, min: number, max: number) {
  if (!Number.isFinite(value)) return min;
  return Math.max(min, Math.min(max, value));
}

function latLngToVector3(lat: number, lng: number, radius: number) {
  const phi = THREE.MathUtils.degToRad(90 - clampNumber(lat, -89.5, 89.5));
  const theta = THREE.MathUtils.degToRad(lng + 180);
  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta),
  );
}

function currentSunDirection() {
  const now = new Date();
  const utcHours = now.getUTCHours() + now.getUTCMinutes() / 60 + now.getUTCSeconds() / 3600;
  const startOfYear = Date.UTC(now.getUTCFullYear(), 0, 0);
  const dayOfYear = Math.floor((Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()) - startOfYear) / 86_400_000);
  const subsolarLatitude = 23.44 * Math.sin((2 * Math.PI * (dayOfYear - 80)) / 365.2422);
  const subsolarLongitude = 180 - utcHours * 15;
  return latLngToVector3(subsolarLatitude, subsolarLongitude, 1).normalize();
}

function makeArc(start: THREE.Vector3, end: THREE.Vector3) {
  const mid = start.clone().add(end).normalize().multiplyScalar(1.38);
  const curve = new THREE.QuadraticBezierCurve3(start.clone().multiplyScalar(1.035), mid, end.clone().multiplyScalar(1.035));
  return curve.getPoints(52);
}

function rotationToCenter(lat: number, lng: number) {
  const vector = latLngToVector3(lat, lng, 1);
  const yRotation = Math.atan2(-vector.x, vector.z);
  const aligned = vector.clone().applyAxisAngle(new THREE.Vector3(0, 1, 0), yRotation);
  const xRotation = clampNumber(Math.atan2(aligned.y, aligned.z), -0.74, 0.74);
  return { x: xRotation, y: yRotation };
}

export default function AtlasGlobe3D({ hub, nodes, language, remoteConnected }: AtlasGlobe3DProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{ pointerId: number; x: number; y: number; rotationX: number; rotationY: number } | null>(null);
  const resetViewRef = useRef<() => void>(() => undefined);
  const [webglReady, setWebglReady] = useState(false);
  const focusNode = useMemo(
    () => nodes.find((node) => node.role === "my_node" || node.key === "anon-region-my-node") ?? { ...hub, key: "hub", activity: 1, source: "local", state: "active", role: "seoul_hub" },
    [hub, nodes],
  );
  const initialRotation = useMemo(() => rotationToCenter(focusNode.lat, focusNode.lng), [focusNode.lat, focusNode.lng]);
  const rotationRef = useRef(initialRotation);
  const safeNodes = useMemo(
    () => nodes
      .filter((node) => Number.isFinite(node.lat) && Number.isFinite(node.lng))
      .slice(0, 96),
    [nodes],
  );
  const nodeSignature = useMemo(
    () => safeNodes
      .map((node) => `${node.key}:${node.role ?? ""}:${node.state}:${node.lat.toFixed(2)}:${node.lng.toFixed(2)}:${node.activity.toFixed(2)}`)
      .join("|"),
    [safeNodes],
  );
  const sourceNodeCount = nodes.length;

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;

    let disposed = false;
    let loadedTextureCount = 0;
    host.dataset.ready = "false";
    setWebglReady(false);
    const markTextureReady = () => {
      loadedTextureCount += 1;
      if (!disposed && loadedTextureCount >= 3) {
        host.dataset.ready = "true";
        setWebglReady(true);
      }
    };
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    camera.position.set(0, 0, 3.55);
    rotationRef.current = initialRotation;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    const pixelRatio = resolveGraphPixelRatio(window.devicePixelRatio);
    renderer.setPixelRatio(pixelRatio);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    host.appendChild(renderer.domElement);

    const group = new THREE.Group();
    group.rotation.x = rotationRef.current.x;
    group.rotation.y = rotationRef.current.y;
    scene.add(group);

    const loader = new THREE.TextureLoader();
    const dayTexture = loader.load("/atlas/earth_atmos_2048.jpg", markTextureReady, undefined, markTextureReady);
    const nightTexture = loader.load("/atlas/earth_lights_2048.png", markTextureReady, undefined, markTextureReady);
    const cloudTexture = loader.load("/atlas/earth_clouds_1024.png", markTextureReady, undefined, markTextureReady);
    [dayTexture, nightTexture, cloudTexture].forEach((texture) => {
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.anisotropy = 8;
    });

    const sunDirection = currentSunDirection();
    const earthMaterial = new THREE.ShaderMaterial({
      uniforms: {
        dayTexture: { value: dayTexture },
        nightTexture: { value: nightTexture },
        sunDirection: { value: sunDirection },
        cameraPositionLocal: { value: new THREE.Vector3(0, 0, 3.55) },
      },
      vertexShader: `
        varying vec2 vUv;
        varying vec3 vNormalLocal;
        varying vec3 vPositionLocal;
        void main() {
          vUv = uv;
          vNormalLocal = normalize(normal);
          vPositionLocal = position;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform sampler2D dayTexture;
        uniform sampler2D nightTexture;
        uniform vec3 sunDirection;
        uniform vec3 cameraPositionLocal;
        varying vec2 vUv;
        varying vec3 vNormalLocal;
        varying vec3 vPositionLocal;
        void main() {
          vec3 normalLocal = normalize(vNormalLocal);
          vec3 sun = normalize(sunDirection);
          float sunlight = dot(normalLocal, sun);
          float dayMix = smoothstep(-0.16, 0.2, sunlight);
          vec3 dayColor = texture2D(dayTexture, vUv).rgb;
          dayColor = pow(dayColor, vec3(0.96));
          dayColor = dayColor * 1.06;
          vec3 nightColor = texture2D(nightTexture, vUv).rgb * 1.38;
          vec3 viewDirection = normalize(cameraPositionLocal - vPositionLocal);
          float fresnel = pow(1.0 - max(dot(normalLocal, viewDirection), 0.0), 2.7);
          float oceanMask = smoothstep(0.14, 0.55, dayColor.b - max(dayColor.r, dayColor.g) * 0.42);
          float specular = pow(max(dot(reflect(-sun, normalLocal), viewDirection), 0.0), 36.0) * oceanMask * smoothstep(0.02, 0.6, sunlight);
          float terminator = 1.0 - smoothstep(0.0, 0.2, abs(sunlight));
          vec3 twilight = vec3(0.58, 0.70, 0.86) * terminator * 0.06;
          vec3 atmosphere = vec3(0.44, 0.72, 1.0) * fresnel * (0.08 + dayMix * 0.16);
          vec3 color = mix(nightColor, dayColor * (0.98 + max(sunlight, 0.0) * 0.16), dayMix);
          color += twilight + atmosphere + specular * vec3(0.88, 0.96, 1.0);
          gl_FragColor = vec4(color, 1.0);
        }
      `,
    });

    const earth = new THREE.Mesh(new THREE.SphereGeometry(1, 96, 96), earthMaterial);
    group.add(earth);

    const clouds = new THREE.Mesh(
      new THREE.SphereGeometry(1.012, 64, 64),
      new THREE.MeshStandardMaterial({
        map: cloudTexture,
        transparent: true,
        opacity: 0.045,
        depthWrite: false,
        blending: THREE.NormalBlending,
      }),
    );
    group.add(clouds);

    const atmosphere = new THREE.Mesh(
      new THREE.SphereGeometry(1.035, 64, 64),
      new THREE.MeshBasicMaterial({
        color: 0x7bbcff,
        transparent: true,
        opacity: 0.038,
        side: THREE.BackSide,
        blending: THREE.AdditiveBlending,
      }),
    );
    group.add(atmosphere);

    const ambient = new THREE.AmbientLight(0xffffff, 0.72);
    scene.add(ambient);
    const sunLight = new THREE.DirectionalLight(0xfff0d0, 1.4);
    scene.add(sunLight);

    const visibleNodeCount = Math.max(sourceNodeCount, safeNodes.length, 1);
    const densityScale = clampNumber(Math.sqrt(96 / visibleNodeCount), 0.32, 1);
    const haloDensityScale = clampNumber(densityScale * 0.9, 0.24, 1);
    const markerGeometry = new THREE.SphereGeometry(0.014, 14, 14);
    const haloGeometry = new THREE.SphereGeometry(0.038, 18, 18);
    const previewMaterial = new THREE.MeshBasicMaterial({ color: 0xff9f1c });
    const myNodeMaterial = new THREE.MeshBasicMaterial({ color: 0x58d86b });
    const haloMaterial = new THREE.MeshBasicMaterial({
      color: 0xff8a00,
      transparent: true,
      opacity: 0.16,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const hubMaterial = new THREE.MeshBasicMaterial({ color: 0xfff7dc });
    const myHaloMaterial = new THREE.MeshBasicMaterial({
      color: 0x58d86b,
      transparent: true,
      opacity: 0.28,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const hubVector = latLngToVector3(hub.lat, hub.lng, 1.045);

    const hubMarker = new THREE.Mesh(new THREE.SphereGeometry(0.026, 18, 18), hubMaterial);
    hubMarker.position.copy(hubVector);
    group.add(hubMarker);

    const ringMaterial = new THREE.MeshBasicMaterial({
      color: 0xff9f1c,
      transparent: true,
      opacity: 0.52,
      side: THREE.DoubleSide,
    });
    const hubRing = new THREE.Mesh(new THREE.TorusGeometry(0.05, 0.003, 8, 40), ringMaterial);
    hubRing.position.copy(hubVector.clone().multiplyScalar(1.006));
    hubRing.lookAt(hubVector.clone().multiplyScalar(2));
    group.add(hubRing);

    const arcMaterial = new THREE.LineDashedMaterial({
      color: 0xff8a00,
      transparent: true,
      opacity: remoteConnected ? 0.48 : 0.22,
      blending: THREE.AdditiveBlending,
      dashSize: 0.045,
      gapSize: 0.035,
      scale: 1,
    });
    const pulseMaterial = new THREE.MeshBasicMaterial({
      color: 0xff9f1c,
      transparent: true,
      opacity: 0.78,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const pulseGeometry = new THREE.SphereGeometry(0.009, 10, 10);
    const relayPulses: Array<{ mesh: THREE.Mesh; points: THREE.Vector3[]; phase: number; strength: number }> = [];

    safeNodes.forEach((node) => {
      const vector = latLngToVector3(node.lat, node.lng, 1.046);
      const isMyNode = node.role === "my_node" || node.key === "anon-region-my-node";
      const marker = new THREE.Mesh(markerGeometry, isMyNode ? myNodeMaterial : previewMaterial);
      const scale = 0.85 + clampNumber(node.activity, 0.1, 1) * 1.6;
      marker.scale.setScalar((isMyNode ? scale * 1.55 : scale) * densityScale);
      marker.position.copy(vector);
      group.add(marker);
      const halo = new THREE.Mesh(haloGeometry, isMyNode ? myHaloMaterial : haloMaterial);
      halo.scale.setScalar((isMyNode ? scale * 1.85 : scale) * haloDensityScale);
      halo.position.copy(vector.clone().multiplyScalar(1.003));
      group.add(halo);

      if (node.key !== "anon-region-seoul-hub") {
        const arcPoints = makeArc(vector, hubVector);
        const arcGeometry = new THREE.BufferGeometry().setFromPoints(arcPoints);
        const arc = new THREE.Line(arcGeometry, arcMaterial);
        arc.computeLineDistances();
        group.add(arc);
        const isContributingSignal = isMyNode || node.state === "active" || node.state === "syncing";
        if (isContributingSignal) {
          for (let index = 0; index < (isMyNode ? 3 : 1); index += 1) {
            const pulse = new THREE.Mesh(pulseGeometry, pulseMaterial);
            pulse.scale.setScalar((isMyNode ? 1.45 : 1) * densityScale);
            pulse.position.copy(vector);
            group.add(pulse);
            relayPulses.push({
              mesh: pulse,
              points: arcPoints,
              phase: index / (isMyNode ? 3 : 1),
              strength: isMyNode ? 1 : 0.62,
            });
          }
        }
      }
    });

    const resize = () => {
      if (disposed) return;
      const rect = host.getBoundingClientRect();
      const width = Math.max(320, Math.floor(rect.width));
      const height = Math.max(320, Math.floor(rect.height));
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
    };

    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(host);
    resize();

    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    resetViewRef.current = () => {
      rotationRef.current = { ...initialRotation };
      dragRef.current = null;
      host.dataset.dragging = "false";
    };
    let frame = 0;
    let visibilityPaused = typeof document !== "undefined" ? document.hidden : false;
    let memorySafeMode = false;
    let lastMemoryProbeAt = 0;
    let lastRenderedAt = 0;
    const onVisibilityChange = () => {
      visibilityPaused = document.hidden;
      lastRenderedAt = 0;
      host.dataset.visibilityPaused = String(visibilityPaused);
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    const animate = (now = performance.now()) => {
      if (disposed) return;
      frame = window.requestAnimationFrame(animate);
      if (now - lastMemoryProbeAt > 1000) {
        lastMemoryProbeAt = now;
        memorySafeMode = browserMemorySafeMode(chromeHeapSnapshot());
      }
      const fpsCap = graphRenderFpsCap({ denseGraph: sourceNodeCount > 32, memorySafeMode, visibilityPaused });
      writeGraphTelemetry(host, {
        geometriesCount: 8 + relayPulses.length,
        materializedNodes: safeNodes.length,
        materialsCount: 10,
        memorySafeMode,
        pixelRatio,
        renderFpsCap: fpsCap,
        renderedEdges: relayPulses.length,
        texturesCount: 3,
        visibilityPaused,
        visualHints: relayPulses.length,
      });
      if (visibilityPaused || !shouldRenderGraphFrame(now, lastRenderedAt, fpsCap)) return;
      lastRenderedAt = now;
      const sun = currentSunDirection();
      earthMaterial.uniforms.sunDirection.value.copy(sun);
      sunLight.position.copy(sun.clone().multiplyScalar(4));
      earthMaterial.uniforms.cameraPositionLocal.value.set(0, 0, camera.position.z);
      clouds.rotation.y += prefersReducedMotion ? 0.00012 : 0.00042;
      hubRing.scale.setScalar(1 + Math.sin(performance.now() / 760) * 0.09);
      arcMaterial.opacity = (remoteConnected ? 0.34 : 0.16) + Math.max(0, Math.sin(performance.now() / 1800)) * 0.055;
      arcMaterial.scale = 1 + (performance.now() / 1000) % 1;
      haloMaterial.opacity = 0.1 + Math.max(0, Math.sin(performance.now() / 1300)) * 0.07;
      myHaloMaterial.opacity = 0.24 + Math.max(0, Math.sin(performance.now() / 1100)) * 0.14;
      relayPulses.forEach((pulse, index) => {
        const progress = prefersReducedMotion ? pulse.phase : (performance.now() / 2800 + pulse.phase + index * 0.013) % 1;
        const pointIndex = Math.min(pulse.points.length - 1, Math.max(0, Math.floor(progress * (pulse.points.length - 1))));
        const fade = Math.sin(progress * Math.PI);
        pulse.mesh.position.copy(pulse.points[pointIndex]);
        pulse.mesh.visible = remoteConnected || pulse.strength > 0.9;
        pulse.mesh.scale.setScalar((0.62 + fade * 1.45) * densityScale * pulse.strength);
        (pulse.mesh.material as THREE.MeshBasicMaterial).opacity = (0.22 + fade * 0.68) * pulse.strength;
      });
      group.rotation.x = rotationRef.current.x;
      group.rotation.y = rotationRef.current.y;
      renderer.render(scene, camera);
    };
    animate();

    const onPointerDown = (event: PointerEvent) => {
      if (event.button !== 0) return;
      renderer.domElement.setPointerCapture(event.pointerId);
      dragRef.current = {
        pointerId: event.pointerId,
        x: event.clientX,
        y: event.clientY,
        rotationX: rotationRef.current.x,
        rotationY: rotationRef.current.y,
      };
      host.dataset.dragging = "true";
    };
    const onPointerMove = (event: PointerEvent) => {
      if (!dragRef.current || dragRef.current.pointerId !== event.pointerId) return;
      const rect = host.getBoundingClientRect();
      const deltaX = rect.width > 0 ? (event.clientX - dragRef.current.x) / rect.width : 0;
      const deltaY = rect.height > 0 ? (event.clientY - dragRef.current.y) / rect.height : 0;
      rotationRef.current.y = dragRef.current.rotationY + deltaX * Math.PI * 1.75;
      rotationRef.current.x = clampNumber(dragRef.current.rotationX + deltaY * Math.PI * 0.72, -0.86, 0.86);
    };
    const onPointerUp = (event: PointerEvent) => {
      if (dragRef.current?.pointerId === event.pointerId) {
        renderer.domElement.releasePointerCapture(event.pointerId);
        dragRef.current = null;
        host.dataset.dragging = "false";
      }
    };
    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    renderer.domElement.addEventListener("pointermove", onPointerMove);
    renderer.domElement.addEventListener("pointerup", onPointerUp);
    renderer.domElement.addEventListener("pointercancel", onPointerUp);

    return () => {
      disposed = true;
      window.cancelAnimationFrame(frame);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("pointermove", onPointerMove);
      renderer.domElement.removeEventListener("pointerup", onPointerUp);
      renderer.domElement.removeEventListener("pointercancel", onPointerUp);
      host.removeChild(renderer.domElement);
      dayTexture.dispose();
      nightTexture.dispose();
      cloudTexture.dispose();
      earth.geometry.dispose();
      earthMaterial.dispose();
      clouds.geometry.dispose();
      (clouds.material as THREE.Material).dispose();
      atmosphere.geometry.dispose();
      (atmosphere.material as THREE.Material).dispose();
      markerGeometry.dispose();
      haloGeometry.dispose();
      previewMaterial.dispose();
      myNodeMaterial.dispose();
      haloMaterial.dispose();
      myHaloMaterial.dispose();
      hubMaterial.dispose();
      ringMaterial.dispose();
      arcMaterial.dispose();
      pulseMaterial.dispose();
      pulseGeometry.dispose();
      renderer.dispose();
    };
  }, [hub.lat, hub.lng, initialRotation, nodeSignature, remoteConnected, sourceNodeCount]);

  return (
    <div className="atanor-atlas-webgl" ref={hostRef} title={language === "ko" ? "마우스로 드래그해 지구를 회전할 수 있습니다." : "Drag to rotate Earth."}>
      {/* Loading overlay is REMOVED from the DOM once ready (React state), not just
          CSS-faded: measured live, the [data-ready] opacity rule never took effect and
          the '불러오는 중' bar stayed painted over the finished globe indefinitely. */}
      {!webglReady ? (
        <div className="atanor-atlas-loading" aria-hidden="true">
          <span className="atanor-atlas-loading-label">{language === "ko" ? "ATANOR ATLAS 불러오는 중…" : "Loading ATANOR ATLAS…"}</span>
          <span className="atanor-atlas-loading-bar"><i /></span>
        </div>
      ) : null}
      <div className="atanor-atlas-webgl-badge">
        <strong>{language === "ko" ? "실시간 태양 경계" : "Live solar terminator"}</strong>
        <span>{remoteConnected ? "REMOTE CONNECTED" : "PREVIEW"}</span>
      </div>
      <button
        className="atanor-atlas-reset-view"
        type="button"
        onClick={() => resetViewRef.current()}
      >
        {language === "ko" ? "내 노드로 복귀" : "Reset to my node"}
      </button>
      <div className="atanor-atlas-webgl-hint">
        {language === "ko" ? "드래그 회전 / 익명 지역 신호만 표시" : "Drag to rotate / Anonymous regional signals only"}
      </div>
    </div>
  );
}
