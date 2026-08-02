from __future__ import annotations

from packages.tabularis_privacy.models import TabularRecord
from packages.tabularis_privacy.synthetic import create_aggregate_records


def test_synthetic_output_has_no_raw_identifier_and_is_marked_synthetic() -> None:
    records = [
        TabularRecord("r1", {"name": "Ada", "age": 31, "zipcode": "12345", "product_category": "books"}),
        TabularRecord("r2", {"name": "Grace", "age": 32, "zipcode": "12349", "product_category": "books"}),
    ]
    output = create_aggregate_records(records)
    assert output
    assert all(record.synthetic for record in output)
    assert all(record.raw_private_data_removed for record in output)
    assert all("Ada" not in record.fields.values() for record in output)

