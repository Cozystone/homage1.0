//! ATANOR Main-Core integrated pipeline.
//!
//! [Input Text] -> [SQC] -> [Fractal Expansion] -> [Wave Interference]
//! -> [Dominant Path]

mod sqc_types;
mod fractal_engine;
mod holographic_compute;
mod entropy_compressor;
mod growth_loop;

use fractal_engine::{fractal_expand, print_tree, AtanorMasterSeed};
use growth_loop::{
    print_growth_report, spawn_background_growth_worker, DeepCoreGraph, GrowthLoopConfig,
    LocalCorpusLicense, LocalSQCSubgraph,
};
use holographic_compute::{print_wave_report, WaveInterferenceSolver};
use sqc_types::{parse_to_sqc, APPLE_SENTENCE_KO};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};
use std::time::Duration;

fn main() {
    let input = APPLE_SENTENCE_KO;
    println!("ATANOR Main-Core Phase 1-3 integrated demo");
    println!("input_text: {input}");

    let sqcs = parse_to_sqc(input);
    println!("\n[1] SQC transform");
    println!("sqc_count: {}", sqcs.len());
    for (index, code) in sqcs.iter().enumerate() {
        println!(
            "SQC[{index}] packed={} bitmap={:#034b} subject={} rel={:?} energy={} domain={:?}",
            code.packed_u32(),
            code.packed_u32(),
            code.subject_id(),
            code.relation_operator(),
            code.energy_level(),
            code.domain()
        );
    }

    println!("\n[2] Fractal Seed Rail");
    let seed = AtanorMasterSeed::default();
    let graph = fractal_expand(&sqcs, &seed);
    println!("hypothesis_nodes_allocated: {}", graph.nodes.len());
    println!("fractal_edges_allocated: {}", graph.edges.len());
    println!("relation_tree:");
    print_tree(&graph);

    println!("\n[3] Topological Holographic Graph");
    let result = WaveInterferenceSolver::solve(&graph);
    print_wave_report(&graph, &result);

    println!("\n[4] Final Dominant Rail");
    println!("dominant_path_node_ids: {:?}", result.dominant_path);
    println!("dominant_energy: {:.6}", result.dominant_energy);

    println!("\n[5] Idle-Time Deep Core Accumulation");
    let mut lawful_local_corpus = sqcs.clone();
    lawful_local_corpus.extend(parse_to_sqc("Kubernetes is useful"));
    lawful_local_corpus.extend(parse_to_sqc("container manages deployment"));
    let lawful_subgraphs = vec![
        LocalSQCSubgraph::new(
            "public-domain-demo/apple-taste",
            LocalCorpusLicense::PublicDomain,
            sqcs.clone(),
        ),
        LocalSQCSubgraph::new(
            "open-access-demo/container-orchestration",
            LocalCorpusLicense::OpenAccess,
            lawful_local_corpus,
        ),
        LocalSQCSubgraph::new(
            "user-provided-demo/local-note",
            LocalCorpusLicense::UserProvided,
            parse_to_sqc("custom local note is useful"),
        ),
        LocalSQCSubgraph::new(
            "unknown-license-demo/rejected",
            LocalCorpusLicense::Unknown,
            parse_to_sqc("unlicensed fragment is ignored"),
        ),
    ];

    let deep_core = Arc::new(Mutex::new(DeepCoreGraph::default()));
    let idle_flag = Arc::new(AtomicBool::new(true));
    let stop_flag = Arc::new(AtomicBool::new(false));

    let worker = spawn_background_growth_worker(
        lawful_subgraphs,
        Arc::clone(&deep_core),
        GrowthLoopConfig {
            idle_rounds: 4,
            ..Default::default()
        },
        Arc::clone(&idle_flag),
        Arc::clone(&stop_flag),
        Duration::from_millis(25),
    );

    // Production idle detection owns these flags. The demo starts in idle mode,
    // lets one bounded local-only synthesis tick run, then requests shutdown so
    // the sample remains deterministic and test-friendly.
    std::thread::sleep(Duration::from_millis(35));
    idle_flag.store(false, Ordering::SeqCst);
    stop_flag.store(true, Ordering::SeqCst);

    let growth_report = worker
        .join()
        .expect("growth loop worker")
        .expect("local-only growth report");
    print_growth_report(&growth_report);

    println!("memory_sqc_bytes: {}", sqcs.len() * std::mem::size_of::<sqc_types::SQC>());
    println!(
        "memory_graph_payload_bytes: {}",
        graph.nodes.len() * std::mem::size_of::<fractal_engine::HypothesisNode>()
            + graph.edges.len() * std::mem::size_of::<fractal_engine::FractalEdge>()
    );
    println!(
        "memory_deep_core_bytes_estimate: {}",
        growth_report.final_nodes * std::mem::size_of::<growth_loop::DeepCoreNode>()
            + growth_report.final_edges * std::mem::size_of::<growth_loop::DeepCoreEdge>()
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn integrated_pipeline_produces_dominant_path() {
        let sqcs = parse_to_sqc(APPLE_SENTENCE_KO);
        let graph = fractal_expand(&sqcs, &AtanorMasterSeed::default());
        let result = WaveInterferenceSolver::solve(&graph);

        assert_eq!(sqcs.len(), 1);
        assert_eq!(graph.nodes.len(), 8);
        assert_eq!(graph.edges.len(), 7);
        assert!(!result.dominant_path.is_empty());
        assert_eq!(result.dominant_path[0], 0);
    }

    #[test]
    fn idle_growth_loop_updates_deep_core() {
        let mut corpus = parse_to_sqc(APPLE_SENTENCE_KO);
        corpus.extend(parse_to_sqc("Kubernetes is useful"));
        let mut deep_core = DeepCoreGraph::default();
        let engine = growth_loop::GrowthLoopEngine::new(GrowthLoopConfig { idle_rounds: 1, ..Default::default() });
        let report = engine.run_idle_accumulation(&corpus, &mut deep_core);

        assert_eq!(report.rounds.len(), 1);
        assert!(report.final_nodes > 0);
    }
}
