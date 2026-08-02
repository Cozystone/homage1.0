from packages.agentic_micro_os.cloud_gateway import CloudGateway


def test_cloud_gateway_draft_and_prod_write():
    gateway = CloudGateway()
    assert gateway.verified_read_summary("x").allowed is True
    assert gateway.candidate_write_draft("x").allowed is True
    assert gateway.production_write("x").allowed is False
