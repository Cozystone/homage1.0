from packages.brain_graph.aggregator import aggregate_brain_graph, brain_graph_status


def test_local_graph_rejects_cloud_layer_as_missing():
    graph = aggregate_brain_graph(view="local", layers=["local_user", "semantic_cloud"], max_nodes=120, max_edges=200)
    assert graph["view"] == "local"
    assert "semantic_cloud" not in graph["stats"]["layer_counts"]
    assert any(item["layer"] == "semantic_cloud" for item in graph["layers_missing"])


def test_cloud_graph_keeps_cloud_attached_out_of_local_count():
    graph = aggregate_brain_graph(view="cloud", layers=["cloud_attached", "working_memory_cloud"], max_nodes=120, max_edges=200)
    assert graph["stats"]["cloud_attached_counts_as_local"] is False
    assert graph["honesty"]["cloud_attached_counts_as_local"] is False


def test_status_lists_separate_views():
    status = brain_graph_status()
    assert "local_user" in status["views"]["local"]["layers"]
    assert "semantic_cloud" in status["views"]["cloud"]["layers"]
