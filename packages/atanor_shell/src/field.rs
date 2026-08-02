//! M2 — the native particle field: layer 0 of the ATANOR surface, drawn by
//! OUR compositor on the CPU. No browser, no DOM, no GL — gaussian point
//! sprites rasterized into a shared memory buffer the renderer composites
//! under every client.
//!
//! The four absolute rules hold here exactly as they did in the web field:
//! points ONLY (this file contains no line rasterizer at all), gaussian
//! self-luminous grains, plain grays, fluid trigonometric drift. The physics
//! is the PureField annulus, ported: a radial band around the screen center,
//! integrated spin (mode changes glide, nothing snaps), inviolable inner gap.

use smithay::backend::allocator::Fourcc;
use smithay::backend::renderer::element::memory::MemoryRenderBuffer;
use smithay::utils::{Rectangle, Transform};

const DEEP_SPACE_BGRA: [u8; 4] = [10, 7, 5, 255];
const GRAYS: [u8; 3] = [0x8e, 0xb0, 0xcc]; // #8b939e/#a8b0ba/#c6ccd4, folded to luma
const SPRITE: usize = 13; // odd => centered gaussian grain

fn gaussian(rng: &mut u64) -> f32 {
    // Box-Muller over a tiny xorshift — no rand crate for one distribution
    let mut next = || {
        *rng ^= *rng << 13;
        *rng ^= *rng >> 7;
        *rng ^= *rng << 17;
        (*rng as f64 / u64::MAX as f64) as f32
    };
    let (mut u, v) = (next(), next());
    if u <= 1e-7 {
        u = 1e-7;
    }
    (-2.0 * u.ln()).sqrt() * (2.0 * std::f32::consts::PI * v).cos()
}

pub struct ParticleField {
    w: i32,
    h: i32,
    radius: Vec<f32>,
    theta: Vec<f32>,
    phi: Vec<f32>,
    phase: Vec<f32>,
    shade: Vec<u8>,
    spin: f32,
    t: f32,
    sprite: [[u8; SPRITE]; SPRITE],
    pub buffer: MemoryRenderBuffer,
}

impl ParticleField {
    pub fn new(w: i32, h: i32, budget: usize) -> Self {
        let mut rng: u64 = 0x5eed_a7a0_0b5e_55e5;
        let mut uniform = move || {
            rng ^= rng << 13;
            rng ^= rng >> 7;
            rng ^= rng << 17;
            (rng as f64 / u64::MAX as f64) as f32
        };
        let mut grng: u64 = 0x1234_5678_9abc_def1;
        let n = budget.max(600);
        let mut radius = Vec::with_capacity(n);
        let mut theta = Vec::with_capacity(n);
        let mut phi = Vec::with_capacity(n);
        let mut phase = Vec::with_capacity(n);
        let mut shade = Vec::with_capacity(n);
        for _ in 0..n {
            // tight halo band around the (future) orb — same constants as the web field
            radius.push(2.5 + (gaussian(&mut grng).abs() * 0.7).min(0.95));
            theta.push(uniform() * std::f32::consts::TAU);
            phi.push((2.0 * uniform() - 1.0).acos());
            phase.push(uniform() * std::f32::consts::TAU);
            shade.push(GRAYS[(uniform() * 3.0) as usize % 3]);
        }
        let mut sprite = [[0u8; SPRITE]; SPRITE];
        let c = (SPRITE / 2) as f32;
        for (y, row) in sprite.iter_mut().enumerate() {
            for (x, px) in row.iter_mut().enumerate() {
                let d2 = (x as f32 - c).powi(2) + (y as f32 - c).powi(2);
                *px = (255.0 * (-d2 / (2.0 * 2.6 * 2.6)).exp()) as u8;
            }
        }
        let buffer = MemoryRenderBuffer::new(Fourcc::Argb8888, (w, h), 1, Transform::Normal, None);
        Self { w, h, radius, theta, phi, phase, shade, spin: 0.0, t: 0.0, sprite, buffer }
    }

    /// Idle physics for now (M3 wires engine state -> mode tempo, like the web).
    pub fn step(&mut self, dt: f32) {
        self.t += dt;
        self.spin += 0.05 * dt;
    }

    pub fn rasterize(&mut self) {
        let (w, h) = (self.w, self.h);
        let unit = h as f32 * 0.127; // matches the web calibration: inner gap ~2.35u
        let (cx, cy) = (w as f32 / 2.0, h as f32 * 0.48);
        let n = self.radius.len();
        let t = self.t;
        let spin = self.spin;
        let radius = &self.radius;
        let theta = &self.theta;
        let phi = &self.phi;
        let phase = &self.phase;
        let shade = &self.shade;
        let sprite = &self.sprite;
        let _ = self.buffer.render().draw::<_, std::convert::Infallible>(|buf| {
            for px in buf.chunks_exact_mut(4) {
                px.copy_from_slice(&DEEP_SPACE_BGRA);
            }
            for i in 0..n {
                let p = phase[i];
                let mut r = radius[i] + (t * 0.35 + p).sin() * 0.12; // loose breathing
                if r < 2.35 {
                    r = 2.35; // the gap is inviolable
                }
                let th = theta[i] + spin * (0.65 + 0.35 * p.sin());
                let ph = phi[i] + ((t * 0.05 + p).sin()) * 0.06;
                let sr = ph.sin() * r;
                let x = cx + (th.cos() * sr + (t * 0.07 + p * 1.7).sin() * 0.08) * unit;
                let y = cy + (ph.cos() * r * 0.78 + (t * 0.06 + p).cos() * 0.08) * unit;
                let depth = 0.55 + 0.45 * (0.5 + 0.5 * (th.sin() * sr * 0.6)); // photons, not dust
                let g = shade[i] as f32 * depth.min(1.0);
                let (x0, y0) = (x as i32 - (SPRITE as i32) / 2, y as i32 - (SPRITE as i32) / 2);
                for (sy, row) in sprite.iter().enumerate() {
                    let yy = y0 + sy as i32;
                    if yy < 0 || yy >= h {
                        continue;
                    }
                    for (sx, &a) in row.iter().enumerate() {
                        let xx = x0 + sx as i32;
                        if xx < 0 || xx >= w || a == 0 {
                            continue;
                        }
                        let idx = ((yy * w + xx) * 4) as usize;
                        let add = (g * a as f32 / 255.0) as u16;
                        // soft luminous accumulation — grays stay gray on deep space
                        buf[idx] = (buf[idx] as u16 + add).min(255) as u8;
                        buf[idx + 1] = (buf[idx + 1] as u16 + add).min(255) as u8;
                        buf[idx + 2] = (buf[idx + 2] as u16 + add).min(255) as u8;
                    }
                }
            }
            Ok(vec![Rectangle::from_size((w, h).into())])
        });
    }
}
