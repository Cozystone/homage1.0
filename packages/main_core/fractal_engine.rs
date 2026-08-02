//! ATANOR Main-Core Phase 2: Fractal Seed Rail.
//!
//! The engine receives text-free SQC atoms and expands them into deterministic
//! hypothesis paths. This is algorithmic graph cell division, not DB retrieval.

use crate::sqc_types::{Domain, RelationOperator, SQC};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum CausalOperator {
    GroundedObservation = 0,
    PropertyImplication = 1,
    DomainAnalogy = 2,
    ContrastCheck = 3,
    EvidenceNeed = 4,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct HypothesisNode {
    pub id: u32,
    pub parent_id: Option<u32>,
    pub sqc: SQC,
    pub depth: u8,
    pub branch_index: u8,
    pub causal_operator: CausalOperator,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FractalEdge {
    pub source_id: u32,
    pub target_id: u32,
    pub operator: CausalOperator,
    pub strength: u8,
}

#[derive(Debug, Default)]
pub struct FractalGraph {
    pub nodes: Vec<HypothesisNode>,
    pub edges: Vec<FractalEdge>,
}

pub trait MasterSeed {
    fn max_depth(&self) -> u8;
    fn branching_factor(&self, sqc: SQC, depth: u8) -> u8;
    fn branch_operator(&self, parent: &HypothesisNode, branch_index: u8) -> CausalOperator;
    fn edge_strength(&self, parent: &HypothesisNode, operator: CausalOperator) -> u8;
    fn child_sqc(&self, parent: &HypothesisNode, branch_index: u8, operator: CausalOperator) -> SQC;
}

#[derive(Debug, Clone, Copy)]
pub struct AtanorMasterSeed {
    max_depth: u8,
}

impl Default for AtanorMasterSeed {
    fn default() -> Self {
        Self { max_depth: 2 }
    }
}

impl MasterSeed for AtanorMasterSeed {
    fn max_depth(&self) -> u8 {
        self.max_depth
    }

    fn branching_factor(&self, sqc: SQC, depth: u8) -> u8 {
        if depth >= self.max_depth {
            return 0;
        }

        match (sqc.relation_operator(), depth) {
            (RelationOperator::HasProperty, 0) => 3,
            (RelationOperator::HasProperty, 1) => 2,
            (_, 0) => 2,
            (_, 1) => 1,
            _ => 0,
        }
    }

    fn branch_operator(&self, parent: &HypothesisNode, branch_index: u8) -> CausalOperator {
        match (parent.depth, branch_index) {
            (0, 0) => CausalOperator::PropertyImplication,
            (0, 1) => CausalOperator::DomainAnalogy,
            (0, _) => CausalOperator::ContrastCheck,
            (_, 0) => CausalOperator::EvidenceNeed,
            (_, _) => CausalOperator::PropertyImplication,
        }
    }

    fn edge_strength(&self, parent: &HypothesisNode, operator: CausalOperator) -> u8 {
        let base = parent.sqc.energy_level().saturating_add(8);
        match operator {
            CausalOperator::GroundedObservation => base.min(63),
            CausalOperator::PropertyImplication => base.saturating_sub(4).min(63),
            CausalOperator::DomainAnalogy => base.saturating_sub(12).min(63),
            CausalOperator::ContrastCheck => 24,
            CausalOperator::EvidenceNeed => 36,
        }
    }

    fn child_sqc(&self, parent: &HypothesisNode, branch_index: u8, operator: CausalOperator) -> SQC {
        let subject_id = derive_subject_id(parent.sqc.subject_id(), parent.depth, branch_index);
        let relation = match operator {
            CausalOperator::PropertyImplication => RelationOperator::Causes,
            CausalOperator::DomainAnalogy => RelationOperator::HasProperty,
            CausalOperator::ContrastCheck => RelationOperator::ContrastsWith,
            CausalOperator::EvidenceNeed => RelationOperator::Performs,
            CausalOperator::GroundedObservation => parent.sqc.relation_operator(),
        };
        let energy = match operator {
            CausalOperator::PropertyImplication => parent.sqc.energy_level().saturating_sub(4),
            CausalOperator::DomainAnalogy => parent.sqc.energy_level().saturating_sub(10),
            CausalOperator::ContrastCheck => 24,
            CausalOperator::EvidenceNeed => 36,
            CausalOperator::GroundedObservation => parent.sqc.energy_level(),
        };
        let domain = match operator {
            CausalOperator::DomainAnalogy if parent.sqc.domain() == Domain::FoodTaste => Domain::Biology,
            _ => parent.sqc.domain(),
        };

        SQC::new(subject_id, relation, energy, domain)
    }
}

pub fn fractal_expand(input: &[SQC], seed: &impl MasterSeed) -> FractalGraph {
    let mut graph = FractalGraph::default();
    for sqc in input {
        let root_id = graph.nodes.len() as u32;
        graph.nodes.push(HypothesisNode {
            id: root_id,
            parent_id: None,
            sqc: *sqc,
            depth: 0,
            branch_index: 0,
            causal_operator: CausalOperator::GroundedObservation,
        });
        expand_recursive(root_id, seed, &mut graph);
    }
    graph
}

fn expand_recursive(parent_id: u32, seed: &impl MasterSeed, graph: &mut FractalGraph) {
    let parent = graph.nodes[parent_id as usize];
    let branch_count = seed.branching_factor(parent.sqc, parent.depth);

    for branch_index in 0..branch_count {
        let operator = seed.branch_operator(&parent, branch_index);
        let child_id = graph.nodes.len() as u32;
        let child = HypothesisNode {
            id: child_id,
            parent_id: Some(parent_id),
            sqc: seed.child_sqc(&parent, branch_index, operator),
            depth: parent.depth + 1,
            branch_index,
            causal_operator: operator,
        };
        graph.edges.push(FractalEdge {
            source_id: parent_id,
            target_id: child_id,
            operator,
            strength: seed.edge_strength(&parent, operator),
        });
        graph.nodes.push(child);

        if child.depth < seed.max_depth() {
            expand_recursive(child_id, seed, graph);
        }
    }
}

fn derive_subject_id(parent_subject_id: u16, depth: u8, branch_index: u8) -> u16 {
    let raw = parent_subject_id as u32 + ((depth as u32 + 1) * 97) + ((branch_index as u32 + 1) * 31);
    let masked = (raw & 0x0fff) as u16;
    if masked == 0 { 1 } else { masked }
}

pub fn print_tree(graph: &FractalGraph) {
    for root in graph.nodes.iter().filter(|node| node.parent_id.is_none()) {
        print_node(graph, root.id, "", true);
    }
}

fn print_node(graph: &FractalGraph, node_id: u32, prefix: &str, is_last: bool) {
    let node = graph.nodes[node_id as usize];
    let branch = if node.parent_id.is_none() {
        ""
    } else if is_last {
        "`- "
    } else {
        "|- "
    };

    println!(
        "{prefix}{branch}node#{} depth={} op={:?} sqc={} subject={} rel={:?} energy={} domain={:?}",
        node.id,
        node.depth,
        node.causal_operator,
        node.sqc.packed_u32(),
        node.sqc.subject_id(),
        node.sqc.relation_operator(),
        node.sqc.energy_level(),
        node.sqc.domain()
    );

    let children: Vec<u32> = graph
        .edges
        .iter()
        .filter(|edge| edge.source_id == node_id)
        .map(|edge| edge.target_id)
        .collect();
    let child_prefix = if node.parent_id.is_none() {
        String::new()
    } else if is_last {
        format!("{prefix}   ")
    } else {
        format!("{prefix}|  ")
    };

    for (index, child_id) in children.iter().enumerate() {
        print_node(graph, *child_id, &child_prefix, index + 1 == children.len());
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::sqc_types::{parse_to_sqc, APPLE_SENTENCE_KO};

    #[test]
    fn apple_sqc_expands_into_deterministic_tree() {
        let sqcs = parse_to_sqc(APPLE_SENTENCE_KO);
        let graph = fractal_expand(&sqcs, &AtanorMasterSeed::default());
        assert_eq!(graph.nodes.len(), 8);
        assert_eq!(graph.edges.len(), 7);
        assert_eq!(graph.nodes[0].sqc.subject_id(), 0x101);
        assert_eq!(graph.nodes[1].parent_id, Some(0));
    }

    #[test]
    fn edge_count_is_nodes_minus_roots() {
        let sqcs = parse_to_sqc(APPLE_SENTENCE_KO);
        let graph = fractal_expand(&sqcs, &AtanorMasterSeed::default());
        assert_eq!(graph.edges.len(), graph.nodes.len() - sqcs.len());
    }
}
