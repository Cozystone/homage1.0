//! ATANOR Main-Core Phase 1: Meaning Quantum Code (SQC).
//!
//! SQC is intentionally text-free. Natural language is accepted only at the
//! deterministic parser boundary, then lowered into a compact 32-bit symbolic
//! atom: subject id, relation operator, energy level, and domain.
//!
//! Korean examples are encoded with Unicode escapes so this file stays stable
//! across Windows console encodings.

pub const APPLE_SENTENCE_KO: &str = "\u{C0AC}\u{ACFC}\u{B294} \u{B9DB}\u{C788}\u{B2E4}";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum RelationOperator {
    Unknown = 0,
    IsA = 1,
    HasProperty = 2,
    Performs = 3,
    Causes = 4,
    ContrastsWith = 5,
}

impl RelationOperator {
    pub fn from_bits(value: u8) -> Self {
        match value {
            1 => Self::IsA,
            2 => Self::HasProperty,
            3 => Self::Performs,
            4 => Self::Causes,
            5 => Self::ContrastsWith,
            _ => Self::Unknown,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum Domain {
    Unknown = 0,
    General = 1,
    FoodTaste = 2,
    Technology = 3,
    Biology = 4,
    Social = 5,
}

impl Domain {
    pub fn from_bits(value: u8) -> Self {
        match value {
            1 => Self::General,
            2 => Self::FoodTaste,
            3 => Self::Technology,
            4 => Self::Biology,
            5 => Self::Social,
            _ => Self::Unknown,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SQC {
    bits: u32,
}

impl SQC {
    const SUBJECT_BITS: u32 = 12;
    const RELATION_BITS: u32 = 6;
    const ENERGY_BITS: u32 = 6;
    const DOMAIN_BITS: u32 = 6;

    const SUBJECT_SHIFT: u32 = 0;
    const RELATION_SHIFT: u32 = Self::SUBJECT_SHIFT + Self::SUBJECT_BITS;
    const ENERGY_SHIFT: u32 = Self::RELATION_SHIFT + Self::RELATION_BITS;
    const DOMAIN_SHIFT: u32 = Self::ENERGY_SHIFT + Self::ENERGY_BITS;

    const SUBJECT_MASK: u32 = (1 << Self::SUBJECT_BITS) - 1;
    const RELATION_MASK: u32 = (1 << Self::RELATION_BITS) - 1;
    const ENERGY_MASK: u32 = (1 << Self::ENERGY_BITS) - 1;
    const DOMAIN_MASK: u32 = (1 << Self::DOMAIN_BITS) - 1;

    pub fn new(
        subject_id: u16,
        relation_operator: RelationOperator,
        energy_level: u8,
        domain: Domain,
    ) -> Self {
        let subject = (subject_id as u32) & Self::SUBJECT_MASK;
        let relation = (relation_operator as u32) & Self::RELATION_MASK;
        let energy = (energy_level as u32).min(Self::ENERGY_MASK);
        let domain = (domain as u32) & Self::DOMAIN_MASK;

        Self {
            bits: subject
                | (relation << Self::RELATION_SHIFT)
                | (energy << Self::ENERGY_SHIFT)
                | (domain << Self::DOMAIN_SHIFT),
        }
    }

    pub fn packed_u32(self) -> u32 {
        self.bits
    }

    pub fn subject_id(self) -> u16 {
        ((self.bits >> Self::SUBJECT_SHIFT) & Self::SUBJECT_MASK) as u16
    }

    pub fn relation_operator(self) -> RelationOperator {
        let value = ((self.bits >> Self::RELATION_SHIFT) & Self::RELATION_MASK) as u8;
        RelationOperator::from_bits(value)
    }

    pub fn energy_level(self) -> u8 {
        ((self.bits >> Self::ENERGY_SHIFT) & Self::ENERGY_MASK) as u8
    }

    pub fn domain(self) -> Domain {
        let value = ((self.bits >> Self::DOMAIN_SHIFT) & Self::DOMAIN_MASK) as u8;
        Domain::from_bits(value)
    }
}

pub fn parse_to_sqc(input: &str) -> Vec<SQC> {
    let normalized = input.trim();
    if normalized.is_empty() {
        return Vec::new();
    }

    let (subject, predicate) = split_subject_predicate(normalized);
    let subject_id = symbol_id(subject);
    let relation = classify_relation(predicate);
    let energy = classify_energy(predicate);
    let domain = classify_domain(subject, predicate);

    vec![SQC::new(subject_id, relation, energy, domain)]
}

fn split_subject_predicate(input: &str) -> (&str, &str) {
    const PARTICLES: [&str; 4] = [
        "\u{C740}", // eun
        "\u{B294}", // neun
        "\u{C774}", // i
        "\u{AC00}", // ga
    ];

    for particle in PARTICLES {
        if let Some(index) = input.find(particle) {
            let subject = input[..index].trim();
            let predicate = input[index + particle.len()..].trim();
            if !subject.is_empty() && !predicate.is_empty() {
                return (subject, predicate);
            }
        }
    }
    (input, "")
}

fn symbol_id(token: &str) -> u16 {
    match token.trim() {
        "\u{C0AC}\u{ACFC}" | "apple" | "Apple" => 0x101,
        "\u{CFE0}\u{BC84}\u{B124}\u{D2F0}\u{C2A4}" | "Kubernetes" | "kubernetes" => 0x201,
        "\u{CEE8}\u{D14C}\u{C774}\u{B108}" | "container" | "Container" => 0x202,
        _ => stable_12bit_hash(token),
    }
}

fn stable_12bit_hash(value: &str) -> u16 {
    let mut hash: u32 = 0x811c9dc5;
    for byte in value.as_bytes() {
        hash ^= *byte as u32;
        hash = hash.wrapping_mul(0x01000193);
    }
    let masked = (hash & 0x0fff) as u16;
    if masked == 0 { 1 } else { masked }
}

fn classify_relation(predicate: &str) -> RelationOperator {
    if predicate.contains("\u{B9DB}\u{C788}")
        || predicate.contains("\u{C88B}")
        || predicate.contains("tasty")
    {
        RelationOperator::HasProperty
    } else if predicate.contains("\u{C774}\u{B2E4}") || predicate.contains("is ") || predicate == "is" {
        RelationOperator::IsA
    } else if predicate.contains("\u{D55C}\u{B2E4}") || predicate.contains("manages") || predicate.contains("performs") {
        RelationOperator::Performs
    } else if predicate.contains("\u{B54C}\u{BB38}") || predicate.contains("causes") {
        RelationOperator::Causes
    } else {
        RelationOperator::Unknown
    }
}

fn classify_energy(predicate: &str) -> u8 {
    if predicate.contains("\u{B9DB}\u{C788}")
        || predicate.contains("\u{C88B}")
        || predicate.contains("\u{C720}\u{C6A9}")
    {
        52
    } else if predicate.contains("\u{B098}\u{C058}")
        || predicate.contains("\u{C2EB}")
        || predicate.contains("\u{C704}\u{D5D8}")
    {
        12
    } else if predicate.is_empty() {
        16
    } else {
        32
    }
}

fn classify_domain(subject: &str, predicate: &str) -> Domain {
    if subject.contains("\u{C0AC}\u{ACFC}") || predicate.contains("\u{B9DB}") {
        Domain::FoodTaste
    } else if subject.contains("\u{CFE0}\u{BC84}\u{B124}\u{D2F0}\u{C2A4}")
        || subject.contains("\u{CEE8}\u{D14C}\u{C774}\u{B108}")
    {
        Domain::Technology
    } else {
        Domain::General
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn maps_korean_apple_sentence_to_stable_sqc() {
        let codes = parse_to_sqc(APPLE_SENTENCE_KO);
        assert_eq!(codes.len(), 1);
        assert_eq!(codes[0].subject_id(), 0x101);
        assert_eq!(codes[0].relation_operator(), RelationOperator::HasProperty);
        assert_eq!(codes[0].energy_level(), 52);
        assert_eq!(codes[0].domain(), Domain::FoodTaste);
    }

    #[test]
    fn sqc_is_four_bytes() {
        assert_eq!(std::mem::size_of::<SQC>(), 4);
    }
}
