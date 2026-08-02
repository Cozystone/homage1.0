from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AtanorCoreConfig:
    name: str = "atanor-core-30m"
    vocab_size: int = 256
    context_length: int = 256
    hidden_size: int = 384
    num_layers: int = 8
    num_heads: int = 6
    concept_head: bool = True
    relation_head: bool = True
    verifier_head: bool = True

    @property
    def estimated_parameters(self) -> int:
        embedding = self.vocab_size * self.hidden_size
        transformer = self.num_layers * (12 * self.hidden_size * self.hidden_size)
        heads = self.hidden_size * self.vocab_size
        auxiliary = self.hidden_size * 3 if (self.concept_head or self.relation_head or self.verifier_head) else 0
        return embedding + transformer + heads + auxiliary


class AtanorCoreModel:
    """Shape-only model scaffold. No pretrained weights, no heavy ML dependency."""

    def __init__(self, config: AtanorCoreConfig | None = None) -> None:
        self.config = config or AtanorCoreConfig()
        self.initialization = "random"

    def forward_shape(self, batch_size: int, sequence_length: int) -> tuple[int, int, int]:
        if sequence_length > self.config.context_length:
            raise ValueError("sequence_length exceeds context_length")
        return (batch_size, sequence_length, self.config.vocab_size)

    def summary(self) -> dict:
        return {
            "name": self.config.name,
            "initialization": self.initialization,
            "estimated_parameters": self.config.estimated_parameters,
            "context_length": self.config.context_length,
            "heads": {
                "concept": self.config.concept_head,
                "relation": self.config.relation_head,
                "verifier": self.config.verifier_head,
            },
        }


HomageCoreConfig = AtanorCoreConfig
HomageCoreModel = AtanorCoreModel
