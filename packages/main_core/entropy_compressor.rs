//! ATANOR Main-Core: Knowledge Entropy Compressor.
//!
//! The compressor keeps logical nodes addressable while assigning high-traffic
//! resonant nodes to macro chunks. This is not semantic deletion. The macro
//! chunk is an execution shortcut: frequently co-resonant atoms are pulled into
//! a denser locality so later growth loops can operate on a smaller active
//! frontier while preserving each SQC atom.

use crate::growth_loop::DeepCoreGraph;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct MacroChunk {
    pub id: u32,
    pub anchor_node_id: u32,
    pub member_count: u32,
    pub total_resonance_weight: f64,
}

#[derive(Debug, Clone, Default)]
pub struct EntropyCompressionReport {
    pub macro_chunks_created: u32,
    pub nodes_assigned: u32,
    pub active_macro_chunks: u32,
}

pub fn compress_deep_core_entropy(
    deep_core: &mut DeepCoreGraph,
    reference_threshold: u32,
    weight_threshold: f64,
) -> EntropyCompressionReport {
    let mut report = EntropyCompressionReport::default();
    let mut chunks: Vec<MacroChunk> = Vec::new();

    let candidates: Vec<u32> = deep_core
        .nodes
        .iter()
        .filter(|node| node.reference_count >= reference_threshold || node.resonance_weight >= weight_threshold)
        .map(|node| node.id)
        .collect();

    for anchor_id in candidates {
        let existing_chunk = deep_core.nodes[anchor_id as usize].macro_chunk_id;
        let chunk_id = existing_chunk.unwrap_or_else(|| {
            let id = chunks.len() as u32;
            chunks.push(MacroChunk {
                id,
                anchor_node_id: anchor_id,
                member_count: 0,
                total_resonance_weight: 0.0,
            });
            report.macro_chunks_created += 1;
            id
        });

        assign_resonant_neighborhood(deep_core, chunk_id, anchor_id, &mut report);
    }

    report.active_macro_chunks = deep_core
        .nodes
        .iter()
        .filter_map(|node| node.macro_chunk_id)
        .collect::<std::collections::BTreeSet<u32>>()
        .len() as u32;
    report
}

fn assign_resonant_neighborhood(
    deep_core: &mut DeepCoreGraph,
    chunk_id: u32,
    anchor_id: u32,
    report: &mut EntropyCompressionReport,
) {
    let mut to_assign = vec![anchor_id];
    for edge in &deep_core.edges {
        if edge.source_id == anchor_id && edge.resonance_weight >= 0.45 {
            to_assign.push(edge.target_id);
        }
        if edge.target_id == anchor_id && edge.resonance_weight >= 0.45 {
            to_assign.push(edge.source_id);
        }
    }

    to_assign.sort_unstable();
    to_assign.dedup();

    for node_id in to_assign {
        if let Some(node) = deep_core.nodes.get_mut(node_id as usize) {
            if node.macro_chunk_id != Some(chunk_id) {
                node.macro_chunk_id = Some(chunk_id);
                report.nodes_assigned += 1;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::growth_loop::DeepCoreNode;
    use crate::sqc_types::{Domain, RelationOperator, SQC};

    #[test]
    fn high_reference_nodes_are_assigned_to_macro_chunks() {
        let mut graph = DeepCoreGraph::default();
        graph.nodes.push(DeepCoreNode {
            id: 0,
            sqc: SQC::new(1, RelationOperator::IsA, 40, Domain::General),
            trust: 1.0,
            reference_count: 5,
            resonance_weight: 3.0,
            macro_chunk_id: None,
        });

        let report = compress_deep_core_entropy(&mut graph, 3, 2.5);
        assert_eq!(report.macro_chunks_created, 1);
        assert_eq!(report.nodes_assigned, 1);
        assert_eq!(graph.nodes[0].macro_chunk_id, Some(0));
    }
}
