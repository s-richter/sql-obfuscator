from sql_obfuscator.go_batches import join_batches, split_batches


def test_split_and_join_batches_round_trip_shape():
    script = "SELECT 1\nGO\nSELECT 2"
    batches = split_batches(script)
    assert batches == ["SELECT 1", "SELECT 2"]
    assert join_batches(batches) == "SELECT 1\nGO\nSELECT 2"


def test_split_batches_case_insensitive_go():
    script = "SELECT 1\ngo\nSELECT 2"
    assert split_batches(script) == ["SELECT 1", "SELECT 2"]
