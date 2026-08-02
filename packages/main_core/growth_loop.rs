//! ATANOR Main-Core: Self-Induced Synthesis Growth Loop.
//!
//! This loop is deliberately local and corpus-agnostic. It never downloads or
//! scrapes external archives by itself. A caller may feed it SQC atoms derived
//! from lawful local documents; the loop then pairs distant symbolic packets,
//! expands them through the Fractal Seed Rail, and promotes only constructive
//! holographic paths into the Deep Core graph.

use crate::entropy_compressor::{compress_deep_core_entropy, EntropyCompressionReport};
use crate::fractal_engine::{fractal_expand, AtanorMasterSeed, FractalEdge, HypothesisNode};
use crate::holographic_compute::WaveInterferenceSolver;
use crate::sqc_types::SQC;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};
use std::thread::{self, JoinHandle};
use std::time::Duration;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LocalCorpusLicense {
    PublicDomain,
    OpenAccess,
    UserProvided,
    Unknown,
}

impl LocalCorpusLicense {
    pub fn allows_growth(self) -> bool {
        matches!(
            self,
            LocalCorpusLicense::PublicDomain
                | LocalCorpusLicense::OpenAccess
                | LocalCorpusLicense::UserProvided
        )
    }
}

#[derive(Debug, Clone)]
pub struct LocalSQCSubgraph {
    pub source_id: String,
    pub license: LocalCorpusLicense,
    pub nodes: Vec<SQC>,
}

impl LocalSQCSubgraph {
    pub fn new(source_id: impl Into<String>, license: LocalCorpusLicense, nodes: Vec<SQC>) -> Self {
        Self {
            source_id: source_id.into(),
            license,
            nodes,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GrowthLoopError {
    NoEligibleLocalSubgraphs,
    InsufficientSQCAtoms,
    DeepCoreLockPoisoned,
}

#[derive(Debug, Clone)]
pub struct DeepCoreNode {
    pub id: u32,
    pub sqc: SQC,
    pub trust: f64,
    pub reference_count: u32,
    pub resonance_weight: f64,
    pub macro_chunk_id: Option<u32>,
}

#[derive(Debug, Clone)]
pub struct DeepCoreEdge {
    pub source_id: u32,
    pub target_id: u32,
    pub trust: f64,
    pub resonance_weight: f64,
}

#[derive(Debug, Default)]
pub struct DeepCoreGraph {
    pub nodes: Vec<DeepCoreNode>,
    pub edges: Vec<DeepCoreEdge>,
    pub promoted_paths: u32,
    pub rejected_paths: u32,
}

#[derive(Debug, Clone)]
pub struct GrowthLoopConfig {
    pub idle_rounds: u32,
    pub resonance_threshold: f64,
    pub dissonance_threshold: f64,
    pub entropy_reference_threshold: u32,
    pub entropy_weight_threshold: f64,
}

impl Default for GrowthLoopConfig {
    fn default() -> Self {
        Self {
            idle_rounds: 6,
            resonance_threshold: 1.20,
            dissonance_threshold: -0.08,
            entropy_reference_threshold: 3,
            entropy_weight_threshold: 2.5,
        }
    }
}

#[derive(Debug, Clone)]
pub struct GrowthRoundReport {
    pub round_index: u32,
    pub selected_left: usize,
    pub selected_right: usize,
    pub hypothesis_nodes: usize,
    pub hypothesis_edges: usize,
    pub dominant_energy: f64,
    pub dissonance_index: f64,
    pub promoted: bool,
    pub promoted_nodes: usize,
    pub entropy_report: Option<EntropyCompressionReport>,
}

#[derive(Debug, Default)]
pub struct GrowthLoopReport {
    pub rounds: Vec<GrowthRoundReport>,
    pub final_nodes: usize,
    pub final_edges: usize,
    pub promoted_paths: u32,
    pub rejected_paths: u32,
}

pub struct GrowthLoopEngine {
    seed: AtanorMasterSeed,
    config: GrowthLoopConfig,
}

impl GrowthLoopEngine {
    pub fn new(config: GrowthLoopConfig) -> Self {
        Self {
            seed: AtanorMasterSeed::default(),
            config,
        }
    }

    pub fn run_idle_accumulation_from_subgraphs(
        &self,
        subgraphs: &[LocalSQCSubgraph],
        deep_core: &mut DeepCoreGraph,
    ) -> Result<GrowthLoopReport, GrowthLoopError> {
        let corpus = flatten_lawful_local_subgraphs(subgraphs)?;
        if corpus.len() < 2 {
            return Err(GrowthLoopError::InsufficientSQCAtoms);
        }

        Ok(self.run_idle_accumulation(&corpus, deep_core))
    }

    pub fn run_idle_accumulation(&self, corpus: &[SQC], deep_core: &mut DeepCoreGraph) -> GrowthLoopReport {
        let mut report = GrowthLoopReport::default();
        if corpus.len() < 2 {
            report.final_nodes = deep_core.nodes.len();
            report.final_edges = deep_core.edges.len();
            report.promoted_paths = deep_core.promoted_paths;
            report.rejected_paths = deep_core.rejected_paths;
            return report;
        }

        for round_index in 0..self.config.idle_rounds {
            let (left, right) = select_pair(corpus, round_index);
            let pair = [corpus[left], corpus[right]];
            let hypothesis = fractal_expand(&pair, &self.seed);
            let wave = WaveInterferenceSolver::solve(&hypothesis);
            let dissonance_index = compute_dissonance_index(&hypothesis, deep_core, wave.dominant_energy);
            let promoted = wave.dominant_energy >= self.config.resonance_threshold
                && dissonance_index <= self.config.dissonance_threshold.abs();

            let promoted_nodes = if promoted {
                deep_core.promoted_paths += 1;
                promote_dominant_path(deep_core, &hypothesis, &wave.dominant_path, wave.dominant_energy)
            } else {
                deep_core.rejected_paths += 1;
                0
            };

            let entropy_report = if promoted {
                Some(compress_deep_core_entropy(
                    deep_core,
                    self.config.entropy_reference_threshold,
                    self.config.entropy_weight_threshold,
                ))
            } else {
                None
            };

            report.rounds.push(GrowthRoundReport {
                round_index,
                selected_left: left,
                selected_right: right,
                hypothesis_nodes: hypothesis.nodes.len(),
                hypothesis_edges: hypothesis.edges.len(),
                dominant_energy: wave.dominant_energy,
                dissonance_index,
                promoted,
                promoted_nodes,
                entropy_report,
            });
        }

        report.final_nodes = deep_core.nodes.len();
        report.final_edges = deep_core.edges.len();
        report.promoted_paths = deep_core.promoted_paths;
        report.rejected_paths = deep_core.rejected_paths;
        report
    }
}

pub fn flatten_lawful_local_subgraphs(subgraphs: &[LocalSQCSubgraph]) -> Result<Vec<SQC>, GrowthLoopError> {
    let mut corpus = Vec::new();
    for subgraph in subgraphs {
        if subgraph.license.allows_growth() && !subgraph.source_id.trim().is_empty() {
            corpus.extend(subgraph.nodes.iter().copied());
        }
    }

    if corpus.is_empty() {
        Err(GrowthLoopError::NoEligibleLocalSubgraphs)
    } else {
        Ok(corpus)
    }
}

pub fn spawn_background_growth_worker(
    subgraphs: Vec<LocalSQCSubgraph>,
    deep_core: Arc<Mutex<DeepCoreGraph>>,
    config: GrowthLoopConfig,
    idle_flag: Arc<AtomicBool>,
    stop_flag: Arc<AtomicBool>,
    tick_interval: Duration,
) -> JoinHandle<Result<GrowthLoopReport, GrowthLoopError>> {
    thread::spawn(move || {
        let engine = GrowthLoopEngine::new(config);
        let mut latest_report = GrowthLoopReport::default();

        while !stop_flag.load(Ordering::SeqCst) {
            if idle_flag.load(Ordering::SeqCst) {
                // Causality guard:
                // 1. The worker never asks the network for data.
                // 2. It only consumes caller-provided local SQC subgraphs whose
                //    license scope allows local growth.
                // 3. It transforms two local symbolic regions into a temporary
                //    hypothesis graph, tests that graph through local wave
                //    resonance, then promotes or drops it.
                // 4. Promotion updates DeepCoreGraph; rejection is ordinary
                //    Rust scope-based garbage collection when the temporary
                //    hypothesis graph is dropped.
                let mut core = deep_core
                    .lock()
                    .map_err(|_| GrowthLoopError::DeepCoreLockPoisoned)?;
                latest_report = engine.run_idle_accumulation_from_subgraphs(&subgraphs, &mut core)?;
            }

            thread::sleep(tick_interval);
        }

        Ok(latest_report)
    })
}

fn select_pair(corpus: &[SQC], round_index: u32) -> (usize, usize) {
    let len = corpus.len();
    let left = ((round_index as usize * 3) + 1) % len;
    let mut right = ((round_index as usize * 5) + len / 2 + 1) % len;
    if right == left {
        right = (right + 1) % len;
    }
    (left, right)
}

fn compute_dissonance_index(hypothesis: &crate::fractal_engine::FractalGraph, deep_core: &DeepCoreGraph, dominant_energy: f64) -> f64 {
    if deep_core.nodes.is_empty() {
        return 0.0;
    }

    let mut destructive = 0.0;
    let mut constructive = 0.0;
    for node in &hypothesis.nodes {
        for existing in &deep_core.nodes {
            if node.sqc.subject_id() == existing.sqc.subject_id()
                && node.sqc.relation_operator() != existing.sqc.relation_operator()
            {
                destructive += 0.2 + existing.trust * 0.3;
            } else if node.sqc.subject_id() == existing.sqc.subject_id()
                && node.sqc.relation_operator() == existing.sqc.relation_operator()
            {
                constructive += 0.1 + existing.trust * 0.2;
            }
        }
    }

    (destructive - constructive) / (1.0 + dominant_energy.abs())
}

fn promote_dominant_path(
    deep_core: &mut DeepCoreGraph,
    hypothesis: &crate::fractal_engine::FractalGraph,
    dominant_path: &[u32],
    dominant_energy: f64,
) -> usize {
    let mut promoted = 0;
    let mut previous_deep_id: Option<u32> = None;
    for node_id in dominant_path {
        let hypothesis_node = hypothesis.nodes[*node_id as usize];
        let deep_id = upsert_deep_node(deep_core, hypothesis_node, dominant_energy);
        if let Some(source_id) = previous_deep_id {
            upsert_deep_edge(deep_core, source_id, deep_id, hypothesis, hypothesis_node);
        }
        previous_deep_id = Some(deep_id);
        promoted += 1;
    }
    promoted
}

fn upsert_deep_node(deep_core: &mut DeepCoreGraph, node: HypothesisNode, dominant_energy: f64) -> u32 {
    if let Some(existing) = deep_core
        .nodes
        .iter_mut()
        .find(|candidate| candidate.sqc.packed_u32() == node.sqc.packed_u32())
    {
        existing.reference_count = existing.reference_count.saturating_add(1);
        existing.resonance_weight += dominant_energy.max(0.0);
        existing.trust = 1.0;
        return existing.id;
    }

    let id = deep_core.nodes.len() as u32;
    deep_core.nodes.push(DeepCoreNode {
        id,
        sqc: node.sqc,
        trust: 1.0,
        reference_count: 1,
        resonance_weight: dominant_energy.max(0.0),
        macro_chunk_id: None,
    });
    id
}

fn upsert_deep_edge(
    deep_core: &mut DeepCoreGraph,
    source_id: u32,
    target_id: u32,
    hypothesis: &crate::fractal_engine::FractalGraph,
    hypothesis_node: HypothesisNode,
) {
    let edge_strength = hypothesis
        .edges
        .iter()
        .find(|edge: &&FractalEdge| edge.target_id == hypothesis_node.id)
        .map(|edge| edge.strength as f64 / 63.0)
        .unwrap_or(0.5);

    if let Some(existing) = deep_core
        .edges
        .iter_mut()
        .find(|edge| edge.source_id == source_id && edge.target_id == target_id)
    {
        existing.trust = 1.0;
        existing.resonance_weight += edge_strength;
        return;
    }

    deep_core.edges.push(DeepCoreEdge {
        source_id,
        target_id,
        trust: 1.0,
        resonance_weight: edge_strength,
    });
}

pub fn print_growth_report(report: &GrowthLoopReport) {
    println!("\n[4] Self-Induced Synthesis Loop");
    for round in &report.rounds {
        println!(
            "round={} pair=({}, {}) hypothesis_nodes={} hypothesis_edges={} energy={:.6} dissonance={:.6} promoted={} promoted_nodes={}",
            round.round_index,
            round.selected_left,
            round.selected_right,
            round.hypothesis_nodes,
            round.hypothesis_edges,
            round.dominant_energy,
            round.dissonance_index,
            round.promoted,
            round.promoted_nodes
        );
        if let Some(entropy) = &round.entropy_report {
            println!(
                "  entropy macro_chunks_created={} nodes_assigned={} active_macro_chunks={}",
                entropy.macro_chunks_created,
                entropy.nodes_assigned,
                entropy.active_macro_chunks
            );
        }
    }
    println!(
        "deep_core_final nodes={} edges={} promoted_paths={} rejected_paths={}",
        report.final_nodes, report.final_edges, report.promoted_paths, report.rejected_paths
    );
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::sqc_types::parse_to_sqc;

    #[test]
    fn growth_loop_promotes_constructive_paths_without_external_io() {
        let mut corpus = parse_to_sqc("Kubernetes is useful");
        corpus.extend(parse_to_sqc(crate::sqc_types::APPLE_SENTENCE_KO));
        let engine = GrowthLoopEngine::new(GrowthLoopConfig { idle_rounds: 2, ..Default::default() });
        let mut deep_core = DeepCoreGraph::default();
        let report = engine.run_idle_accumulation(&corpus, &mut deep_core);
        assert_eq!(report.rounds.len(), 2);
        assert!(report.final_nodes > 0);
    }

    #[test]
    fn growth_loop_accepts_only_lawful_local_subgraphs() {
        let allowed = LocalSQCSubgraph::new(
            "public-domain-demo",
            LocalCorpusLicense::PublicDomain,
            parse_to_sqc(crate::sqc_types::APPLE_SENTENCE_KO),
        );
        let blocked = LocalSQCSubgraph::new(
            "unknown-license-demo",
            LocalCorpusLicense::Unknown,
            parse_to_sqc("untrusted corpus fragment"),
        );
        let user_provided = LocalSQCSubgraph::new(
            "user-provided-demo",
            LocalCorpusLicense::UserProvided,
            parse_to_sqc("container manages deployment"),
        );

        let flattened = flatten_lawful_local_subgraphs(&[allowed, blocked, user_provided]).unwrap();
        assert_eq!(flattened.len(), 2);
        assert_eq!(flattened[0].subject_id(), 0x101);
    }

    #[test]
    fn background_worker_runs_only_when_idle_flag_is_set() {
        let subgraphs = vec![
            LocalSQCSubgraph::new(
                "public-domain-demo",
                LocalCorpusLicense::PublicDomain,
                parse_to_sqc(crate::sqc_types::APPLE_SENTENCE_KO),
            ),
            LocalSQCSubgraph::new(
                "open-access-demo",
                LocalCorpusLicense::OpenAccess,
                parse_to_sqc("Kubernetes is useful"),
            ),
        ];
        let deep_core = Arc::new(Mutex::new(DeepCoreGraph::default()));
        let idle_flag = Arc::new(AtomicBool::new(true));
        let stop_flag = Arc::new(AtomicBool::new(false));
        let worker = spawn_background_growth_worker(
            subgraphs,
            Arc::clone(&deep_core),
            GrowthLoopConfig { idle_rounds: 1, ..Default::default() },
            Arc::clone(&idle_flag),
            Arc::clone(&stop_flag),
            Duration::from_millis(5),
        );

        std::thread::sleep(Duration::from_millis(12));
        idle_flag.store(false, Ordering::SeqCst);
        stop_flag.store(true, Ordering::SeqCst);

        let report = worker.join().expect("worker join").expect("growth report");
        assert_eq!(report.rounds.len(), 1);
        assert!(deep_core.lock().unwrap().nodes.len() > 0);
    }
}
