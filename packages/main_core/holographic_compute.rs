//! ATANOR Main-Core Phase 3: Topological Holographic Graph.
//!
//! This module solves the dominant reasoning rail with local wave interference.
//! It does not use embeddings, matrix multiplication, or probabilistic search.

use crate::fractal_engine::{FractalEdge, FractalGraph};

const TAU: f64 = core::f64::consts::PI * 2.0;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Complex {
    pub re: f64,
    pub im: f64,
}

impl Complex {
    pub fn from_polar(amplitude: f64, phase: f64) -> Self {
        Self {
            re: amplitude * phase.cos(),
            im: amplitude * phase.sin(),
        }
    }

    pub fn dot(self, other: Self) -> f64 {
        self.re * other.re + self.im * other.im
    }

    pub fn magnitude(self) -> f64 {
        (self.re * self.re + self.im * self.im).sqrt()
    }
}

#[derive(Debug, Clone, Copy)]
pub struct NodeWave {
    pub node_id: u32,
    pub frequency_bin: u16,
    pub amplitude: f64,
    pub phase: f64,
    pub complex: Complex,
}

#[derive(Debug, Clone, Copy)]
pub struct NodeInterferenceScore {
    pub node_id: u32,
    pub intrinsic_energy: f64,
    pub incoming_interference: f64,
    pub cumulative_energy: f64,
}

#[derive(Debug)]
pub struct WaveInterferenceResult {
    pub waves: Vec<NodeWave>,
    pub scores: Vec<NodeInterferenceScore>,
    pub dominant_path: Vec<u32>,
    pub dominant_energy: f64,
    pub constructive_events: usize,
    pub destructive_events: usize,
}

pub struct WaveInterferenceSolver;

impl WaveInterferenceSolver {
    pub fn solve(graph: &FractalGraph) -> WaveInterferenceResult {
        let waves: Vec<NodeWave> = graph
            .nodes
            .iter()
            .map(|node| {
                let frequency_bin = derive_frequency_bin(
                    node.sqc.subject_id(),
                    node.sqc.packed_u32(),
                    node.depth,
                    node.branch_index,
                );
                let amplitude = derive_amplitude(node.sqc.energy_level(), node.depth);
                let phase = derive_phase(frequency_bin, node.sqc.domain() as u8, node.sqc.relation_operator() as u8);
                NodeWave {
                    node_id: node.id,
                    frequency_bin,
                    amplitude,
                    phase,
                    complex: Complex::from_polar(amplitude, phase),
                }
            })
            .collect();

        let mut scores = Vec::with_capacity(graph.nodes.len());
        let mut cumulative = vec![0.0_f64; graph.nodes.len()];
        let mut incoming = vec![0.0_f64; graph.nodes.len()];
        let mut constructive_events = 0;
        let mut destructive_events = 0;

        for node in &graph.nodes {
            let wave = waves[node.id as usize];
            let intrinsic = wave.complex.magnitude().powi(2);
            if let Some(parent_id) = node.parent_id {
                let edge = find_edge(graph, parent_id, node.id);
                let parent_wave = waves[parent_id as usize];
                let interference = edge
                    .map(|edge| interference_energy(parent_wave, wave, edge))
                    .unwrap_or(0.0);
                if interference >= 0.0 {
                    constructive_events += 1;
                } else {
                    destructive_events += 1;
                }
                incoming[node.id as usize] = interference;
                cumulative[node.id as usize] = cumulative[parent_id as usize] + intrinsic + interference;
            } else {
                cumulative[node.id as usize] = intrinsic;
            }

            scores.push(NodeInterferenceScore {
                node_id: node.id,
                intrinsic_energy: intrinsic,
                incoming_interference: incoming[node.id as usize],
                cumulative_energy: cumulative[node.id as usize],
            });
        }

        let dominant_leaf_id = graph
            .nodes
            .iter()
            .filter(|node| !graph.edges.iter().any(|edge| edge.source_id == node.id))
            .max_by(|left, right| {
                cumulative[left.id as usize]
                    .partial_cmp(&cumulative[right.id as usize])
                    .unwrap_or(core::cmp::Ordering::Equal)
            })
            .map(|node| node.id)
            .unwrap_or(0);
        let dominant_path = extract_path(graph, dominant_leaf_id);
        let dominant_energy = cumulative
            .get(dominant_leaf_id as usize)
            .copied()
            .unwrap_or(0.0);

        WaveInterferenceResult {
            waves,
            scores,
            dominant_path,
            dominant_energy,
            constructive_events,
            destructive_events,
        }
    }
}

fn derive_frequency_bin(subject_id: u16, packed: u32, depth: u8, branch_index: u8) -> u16 {
    let mixed = (subject_id as u32)
        ^ packed.rotate_left(7)
        ^ ((depth as u32) << 9)
        ^ ((branch_index as u32) << 4);
    (mixed & 0x03ff) as u16
}

fn derive_amplitude(energy_level: u8, depth: u8) -> f64 {
    let base = (energy_level as f64 / 63.0).clamp(0.01, 1.0);
    let depth_decay = 1.0 / (1.0 + depth as f64 * 0.18);
    base * depth_decay
}

fn derive_phase(frequency_bin: u16, domain: u8, relation: u8) -> f64 {
    let raw = (frequency_bin as f64 * 0.013_671_875)
        + (domain as f64 * 0.618_033_988_75)
        + (relation as f64 * 0.414_213_562_37);
    raw.rem_euclid(TAU)
}

fn find_edge(graph: &FractalGraph, source_id: u32, target_id: u32) -> Option<&FractalEdge> {
    graph
        .edges
        .iter()
        .find(|edge| edge.source_id == source_id && edge.target_id == target_id)
}

fn interference_energy(parent: NodeWave, child: NodeWave, edge: &FractalEdge) -> f64 {
    let edge_gain = edge.strength as f64 / 63.0;
    parent.complex.dot(child.complex) * edge_gain
}

fn extract_path(graph: &FractalGraph, leaf_id: u32) -> Vec<u32> {
    let mut path = Vec::new();
    let mut cursor = Some(leaf_id);
    while let Some(node_id) = cursor {
        path.push(node_id);
        cursor = graph.nodes[node_id as usize].parent_id;
    }
    path.reverse();
    path
}

pub fn print_wave_report(graph: &FractalGraph, result: &WaveInterferenceResult) {
    println!("wave_nodes: {}", result.waves.len());
    println!("constructive_events: {}", result.constructive_events);
    println!("destructive_events: {}", result.destructive_events);
    println!("dominant_energy: {:.6}", result.dominant_energy);
    println!("dominant_path: {:?}", result.dominant_path);
    for node_id in &result.dominant_path {
        let node = graph.nodes[*node_id as usize];
        let wave = result.waves[*node_id as usize];
        let score = result.scores[*node_id as usize];
        println!(
            "  node#{} wave_node={} score_node={} freq={} amp={:.4} phase={:.4} intrinsic={:.6} incoming={:.6} cumulative={:.6} rel={:?} domain={:?}",
            node.id,
            wave.node_id,
            score.node_id,
            wave.frequency_bin,
            wave.amplitude,
            wave.phase,
            score.intrinsic_energy,
            score.incoming_interference,
            score.cumulative_energy,
            node.sqc.relation_operator(),
            node.sqc.domain()
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::fractal_engine::{fractal_expand, AtanorMasterSeed};
    use crate::sqc_types::{parse_to_sqc, APPLE_SENTENCE_KO};

    #[test]
    fn wave_solver_extracts_a_leaf_dominant_path() {
        let sqcs = parse_to_sqc(APPLE_SENTENCE_KO);
        let graph = fractal_expand(&sqcs, &AtanorMasterSeed::default());
        let result = WaveInterferenceSolver::solve(&graph);

        assert_eq!(result.waves.len(), graph.nodes.len());
        assert_eq!(result.scores.len(), graph.nodes.len());
        assert_eq!(result.dominant_path.first().copied(), Some(0));
        let leaf = *result.dominant_path.last().unwrap();
        assert!(!graph.edges.iter().any(|edge| edge.source_id == leaf));
        assert!(result.dominant_energy.is_finite());
    }

    #[test]
    fn every_edge_is_counted_as_constructive_or_destructive() {
        let sqcs = parse_to_sqc(APPLE_SENTENCE_KO);
        let graph = fractal_expand(&sqcs, &AtanorMasterSeed::default());
        let result = WaveInterferenceSolver::solve(&graph);
        assert_eq!(
            result.constructive_events + result.destructive_events,
            graph.edges.len()
        );
    }
}
