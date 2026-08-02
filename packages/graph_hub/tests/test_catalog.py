from packages.graph_hub.catalog import list_catalog_items, refresh_catalog


def test_catalog_loads_three_pricing_models_and_graph_hub_name():
    refreshed = refresh_catalog()
    rows = list_catalog_items()
    assert refreshed["product_name"] == "Graph Hub"
    assert {"free", "one_time", "subscription"}.issubset({row["pricing_model"] for row in rows})
    assert "Brain Store" not in str(refreshed)


def test_catalog_includes_realistic_sample_graph_fragments():
    refreshed = refresh_catalog()
    rows = list_catalog_items()
    ids = {row["cartridge_id"] for row in rows}
    expected = {
        "graphrag_evidence_verification_demo",
        "local_cloud_boundary_demo",
        "cortex_surface_answer_demo",
    }

    assert expected.issubset(ids)

    by_id = {row["cartridge_id"]: row for row in rows}
    graphrag = by_id["graphrag_evidence_verification_demo"]
    boundary = by_id["local_cloud_boundary_demo"]
    answer = by_id["cortex_surface_answer_demo"]

    assert graphrag["preview"]["semantic_nodes"] >= 10
    assert graphrag["preview"]["semantic_edges"] >= 10
    assert graphrag["preview"]["default_read_only"] is True
    assert "verification" in graphrag["tags"]

    assert boundary["preview"]["semantic_nodes"] >= 10
    assert boundary["preview"]["semantic_edges"] >= 9
    assert boundary["preview"]["default_read_only"] is True
    assert "payload_vault" in boundary["tags"]

    assert answer["preview"]["semantic_nodes"] >= 10
    assert answer["preview"]["semantic_edges"] >= 10
    assert answer["preview"]["default_read_only"] is True
    assert "trace_hygiene" in answer["tags"]
