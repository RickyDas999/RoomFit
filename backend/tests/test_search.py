from app.search import build_query


def test_build_query_per_role() -> None:
    assert build_query("bed", (40, 80)) == "twin xl bed frame"
    assert build_query("desk", (48.7, 24)) == "desk 48 inch"
    assert build_query("desk_chair", (24, 24)) == "desk chair"
    assert build_query("dresser", (36, 18)) == "dresser 36 inch"
    assert build_query("nightstand", (18, 16)) == "nightstand"
