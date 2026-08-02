from __future__ import annotations

import math
import random
from typing import Callable

from packages.splatra_turbovec.models import Particle

from .emotion_bridge import clamp
from .models import Archetype


GOLDEN_ANGLE = math.pi * (3 - math.sqrt(5))


def generate_archetype(archetype: Archetype, count: int, rng: random.Random, controls: dict[str, float]) -> list[Particle]:
    generators: dict[str, Callable[[int, random.Random, dict[str, float]], list[Particle]]] = {
        "orb": orb,
        "tower": tower,
        "tree": tree,
        "creature": creature,
        "circuit": circuit,
        "city_block": city_block,
        "constellation": constellation,
        "machine_core": machine_core,
        "abstract_memory_cloud": abstract_memory_cloud,
    }
    return generators[archetype](max(1, count), rng, controls)


def _particle(
    x: float,
    y: float,
    z: float,
    *,
    color: tuple[float, float, float],
    alpha: float = 0.85,
    radius: float = 0.012,
    material: str = "imagination",
    emotion: float = 0.5,
    audio: float = 0.0,
    velocity: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> Particle:
    return Particle(
        x=clamp(x, -1.95, 1.95),
        y=clamp(y, -1.95, 1.95),
        z=clamp(z, -1.95, 1.95),
        vx=velocity[0],
        vy=velocity[1],
        vz=velocity[2],
        r=clamp(color[0], 0.0, 1.0),
        g=clamp(color[1], 0.0, 1.0),
        b=clamp(color[2], 0.0, 1.0),
        a=clamp(alpha, 0.0, 1.0),
        radius=max(0.002, radius),
        material_id=material,
        emotion_weight=clamp(emotion, 0.0, 1.0),
        audio_reactive_weight=clamp(audio, 0.0, 1.0),
    )


def _palette(controls: dict[str, float], t: float) -> tuple[float, float, float]:
    warmth = float(controls.get("color_warmth", 0.5))
    brightness = float(controls.get("brightness", 0.7))
    cyan = (0.08, 0.88, 1.0)
    blue = (0.1, 0.32, 1.0)
    rose = (1.0, 0.2, 0.52)
    violet = (0.62, 0.28, 1.0)
    a = cyan if t < 0.34 else blue if t < 0.67 else violet
    b = rose
    mix = clamp(warmth * (0.25 + t * 0.45), 0.0, 1.0)
    return tuple(clamp((a[i] * (1 - mix) + b[i] * mix) * brightness, 0.0, 1.0) for i in range(3))


def orb(count: int, rng: random.Random, controls: dict[str, float]) -> list[Particle]:
    shell_count = int(count * 0.52)
    ribbon_count = count - shell_count
    particles: list[Particle] = []
    ripple = float(controls.get("shell_ripple_amplitude", 0.1))
    audio = float(controls.get("speaking_energy", 0.0))
    for i in range(shell_count):
        t = (i + 0.5) / shell_count
        theta = i * GOLDEN_ANGLE
        y = 1 - 2 * t
        ring = math.sqrt(max(0.0, 1 - y * y))
        radius = 1.28 + math.sin(i * 0.037) * ripple * 0.16
        particles.append(_particle(math.cos(theta) * ring * radius, y * radius, math.sin(theta) * ring * radius, color=_palette(controls, t), alpha=0.38, radius=0.007, material="glass_shell", audio=audio))
    for i in range(ribbon_count):
        t = i / max(1, ribbon_count - 1)
        band = i % 3
        angle = t * math.tau * (1.3 + band * 0.18) + band * 1.8
        width = (rng.random() - 0.5) * 0.12
        r = 0.74 + math.sin(angle * 1.7) * 0.22
        x = math.cos(angle) * r
        z = math.sin(angle) * r * (0.46 + band * 0.1)
        y = math.sin(angle * 1.08 + band) * 0.44 + width
        particles.append(_particle(x, y, z, color=_palette(controls, band / 3), alpha=0.9, radius=0.018, material="inner_ribbon", emotion=0.8, audio=audio, velocity=(-z * 0.01, 0.0, x * 0.01)))
    return particles


def tower(count: int, rng: random.Random, controls: dict[str, float]) -> list[Particle]:
    particles = []
    floors = 18
    for i in range(count):
        floor = i % floors
        side = (i // floors) % 4
        y = -1.35 + floor / (floors - 1) * 2.7
        offset = (rng.random() - 0.5) * 0.08
        width = 0.28 + floor * 0.008
        if side == 0:
            x, z = -width, offset
        elif side == 1:
            x, z = width, offset
        elif side == 2:
            x, z = offset, -width
        else:
            x, z = offset, width
        color = _palette(controls, floor / floors)
        particles.append(_particle(x, y, z, color=color, alpha=0.78, radius=0.012, material="tower_window" if rng.random() < 0.35 else "tower_frame"))
    return particles


def tree(count: int, rng: random.Random, controls: dict[str, float]) -> list[Particle]:
    particles = []
    trunk_count = max(1, int(count * 0.26))
    for i in range(trunk_count):
        t = i / trunk_count
        angle = i * GOLDEN_ANGLE
        radius = 0.08 + t * 0.03
        particles.append(_particle(math.cos(angle) * radius, -1.25 + t * 1.5, math.sin(angle) * radius, color=(0.35, 0.58, 0.72), alpha=0.82, radius=0.014, material="trunk"))
    for i in range(count - trunk_count):
        t = i / max(1, count - trunk_count)
        theta = i * GOLDEN_ANGLE
        y = 0.12 + rng.random() * 1.18
        canopy = 0.25 + (1.25 - y) * 0.3
        r = canopy * math.sqrt(rng.random())
        particles.append(_particle(math.cos(theta) * r, y, math.sin(theta) * r, color=_palette(controls, t), alpha=0.66, radius=0.016, material="canopy", emotion=0.7))
    return particles


def creature(count: int, rng: random.Random, controls: dict[str, float]) -> list[Particle]:
    particles = []
    centers = [(-0.28, 0.0, 0.0), (0.26, 0.08, 0.0), (-0.55, -0.42, 0.0), (0.55, -0.42, 0.0), (0.0, 0.58, 0.0)]
    for i in range(count):
        cx, cy, cz = centers[i % len(centers)]
        spread = 0.18 if i % len(centers) != 4 else 0.13
        angle = rng.random() * math.tau
        dist = spread * math.sqrt(rng.random())
        particles.append(_particle(cx + math.cos(angle) * dist, cy + (rng.random() - 0.5) * spread, cz + math.sin(angle) * dist * 0.6, color=_palette(controls, i / count), alpha=0.74, radius=0.015, material="abstract_creature", emotion=0.62))
    return particles


def circuit(count: int, rng: random.Random, controls: dict[str, float]) -> list[Particle]:
    particles = []
    lanes = 8
    for i in range(count):
        lane = i % lanes
        t = (i // lanes) / max(1, count // lanes)
        horizontal = lane % 2 == 0
        coord = -1.1 + lane / (lanes - 1) * 2.2
        wiggle = math.sin(t * math.tau * 3 + lane) * 0.04
        if horizontal:
            x, y, z = -1.2 + t * 2.4, coord + wiggle, 0.05 * math.sin(t * math.tau)
        else:
            x, y, z = coord + wiggle, -1.2 + t * 2.4, 0.05 * math.cos(t * math.tau)
        particles.append(_particle(x, y, z, color=_palette(controls, t), alpha=0.8, radius=0.01 + (0.012 if i % 29 == 0 else 0.0), material="circuit_node" if i % 29 == 0 else "circuit_trace", audio=float(controls.get("speaking_energy", 0.0))))
    return particles


def city_block(count: int, rng: random.Random, controls: dict[str, float]) -> list[Particle]:
    particles = []
    grid = 5
    towers = [(x, z, 0.45 + rng.random() * 1.1) for x in range(grid) for z in range(grid)]
    for i in range(count):
        tx, tz, height = towers[i % len(towers)]
        x0 = -1.1 + tx * 0.55
        z0 = -1.1 + tz * 0.55
        y = -1.25 + rng.random() * height
        face = rng.randrange(4)
        side = 0.12 + rng.random() * 0.08
        x = x0 + (-side if face == 0 else side if face == 1 else (rng.random() - 0.5) * side)
        z = z0 + (-side if face == 2 else side if face == 3 else (rng.random() - 0.5) * side)
        particles.append(_particle(x, y, z, color=_palette(controls, height / 1.6), alpha=0.72, radius=0.009, material="city_window" if rng.random() < 0.45 else "city_mass"))
    return particles


def constellation(count: int, rng: random.Random, controls: dict[str, float]) -> list[Particle]:
    particles = []
    anchors = [(rng.uniform(-1.3, 1.3), rng.uniform(-1.1, 1.1), rng.uniform(-0.8, 0.8)) for _ in range(18)]
    for i in range(count):
        a = anchors[i % len(anchors)]
        b = anchors[(i * 7 + 3) % len(anchors)]
        t = rng.random()
        is_star = i % 11 == 0
        x = a[0] * (1 - t) + b[0] * t + (rng.random() - 0.5) * 0.025
        y = a[1] * (1 - t) + b[1] * t + (rng.random() - 0.5) * 0.025
        z = a[2] * (1 - t) + b[2] * t + (rng.random() - 0.5) * 0.025
        particles.append(_particle(x, y, z, color=_palette(controls, t), alpha=0.92 if is_star else 0.42, radius=0.026 if is_star else 0.006, material="star" if is_star else "implied_line"))
    return particles


def machine_core(count: int, rng: random.Random, controls: dict[str, float]) -> list[Particle]:
    particles = []
    for i in range(count):
        ring = i % 5
        t = i / count
        angle = t * math.tau * (8 + ring) + ring * 0.7
        radius = 0.28 + ring * 0.18 + math.sin(angle * 3) * 0.025
        y = math.sin(angle * (1.0 + ring * 0.08)) * 0.12
        particles.append(_particle(math.cos(angle) * radius, y, math.sin(angle) * radius, color=_palette(controls, ring / 5), alpha=0.82, radius=0.013, material="reactor_ring", velocity=(-math.sin(angle) * 0.015, 0, math.cos(angle) * 0.015)))
    return particles


def abstract_memory_cloud(count: int, rng: random.Random, controls: dict[str, float]) -> list[Particle]:
    particles = []
    centers = [(rng.uniform(-0.8, 0.8), rng.uniform(-0.6, 0.6), rng.uniform(-0.5, 0.5)) for _ in range(7)]
    for i in range(count):
        cx, cy, cz = centers[i % len(centers)]
        spread = 0.18 + rng.random() * 0.36
        theta = rng.random() * math.tau
        phi = math.acos(2 * rng.random() - 1)
        r = spread * (rng.random() ** 0.45)
        particles.append(_particle(cx + math.sin(phi) * math.cos(theta) * r, cy + math.cos(phi) * r, cz + math.sin(phi) * math.sin(theta) * r, color=_palette(controls, i / count), alpha=0.4, radius=0.018, material="abstract_cloud", emotion=0.3))
    return particles
