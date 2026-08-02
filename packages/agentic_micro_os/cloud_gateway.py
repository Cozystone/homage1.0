from __future__ import annotations

from .brain_access import BrainAccessRequest, BrainAccessRoad, BrainAccessResponse


class CloudGateway:
    def __init__(self, road: BrainAccessRoad | None = None) -> None:
        self.road = road or BrainAccessRoad()

    def verified_read_summary(self, query: str, loop_id: str = "loop") -> BrainAccessResponse:
        return self.road.request(
            BrainAccessRequest("cloud_brain", "cloud_brain_verified_read_summary", query, "verified", "public", "proof read", loop_id)
        )

    def candidate_write_draft(self, query: str, loop_id: str = "loop") -> BrainAccessResponse:
        return self.road.request(
            BrainAccessRequest("cloud_brain", "cloud_brain_candidate_write_draft", query, "candidate", "public", "draft only", loop_id)
        )

    def production_write(self, query: str, loop_id: str = "loop") -> BrainAccessResponse:
        return self.road.request(
            BrainAccessRequest("cloud_brain", "production_store_direct_write", query, "production", "public", "forbidden proof", loop_id)
        )
