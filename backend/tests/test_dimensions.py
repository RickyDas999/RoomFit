"""Table-driven tests. Strings are synthetic but shaped like real listing text."""

import pytest

from app.dimensions import Dimensions, parse_dimensions

D = Dimensions

PARSED = [
    # (text, expected W x D x H in inches)
    ('Desk 39"W x 80"D x 14"H', D(w=39, d=80, h=14)),
    ('Size: 39" W x 80" D x 14" H.', D(w=39, d=80, h=14)),
    ("39 x 80 x 14 in", D(w=39, d=80, h=14)),
    ("39 x 80 x 14 inches", D(w=39, d=80, h=14)),
    ("39 X 80 X 14 in", D(w=39, d=80, h=14)),
    ("39×80×14 in", D(w=39, d=80, h=14)),
    ("39 by 80 by 14 in", D(w=39, d=80, h=14)),
    ('48" x 24"', D(w=48, d=24)),  # two numbers: W x D, no height
    ("48'' x 24''", D(w=48, d=24)),  # two apostrophes as inch mark
    ("48” x 24” x 30”", D(w=48, d=24, h=30)),  # curly quotes
    ("Width: 39 in Depth: 20 in", D(w=39, d=20)),
    (
        "Width: 19.3 inches Height: 24.3 inches Length: 15.7 inches",
        D(w=19.3, d=15.7, h=24.3),
    ),
    ("99 cm x 50 cm x 40 cm", D(w=38.98, d=19.69, h=15.75)),
    ("99 x 50 x 40 cm", D(w=38.98, d=19.69, h=15.75)),
    ("990 mm x 500 mm", D(w=38.98, d=19.69)),
    ("3.3 ft x 2 ft", D(w=39.6, d=24)),
    ("3' x 2'", D(w=36, d=24)),
    # order normalization: labels win over position, always returned as W x D x H
    ('14"H x 39"W x 80"D', D(w=39, d=80, h=14)),
    ('30"H x 20"D x 48"W', D(w=48, d=20, h=30)),
    ('36"L x 20"D', D(w=36, d=20)),  # L fills the unlabeled one of W/D
    ('36"Lx20"D', D(w=36, d=20)),
    (
        "Length: 15.7 in Width: 19.3 in",
        D(w=19.3, d=15.7),
    ),  # explicit W wins, L becomes depth
    # context that must NOT block a good match
    (
        'Overall Dimensions: 15" x 11" x 16" Drawer Dimensions: 12.5" x 9" x 4"',
        D(w=15, d=11, h=16),
    ),
    (
        "Great for dorms! Product size 40 x 20 x 30 in. Easy assembly.",
        D(w=40, d=20, h=30),
    ),
]


@pytest.mark.parametrize(("text", "expected"), PARSED)
def test_parsed(text: str, expected: Dimensions) -> None:
    r = parse_dimensions(text)
    assert r.status == "parsed", r
    assert r.dimensions == expected
    assert r.reason is None


def test_parsed_source_is_a_slice_of_the_text() -> None:
    for text, _ in PARSED:
        r = parse_dimensions(text)
        assert r.source
        assert all(piece in text for piece in r.source.split(" … ")), (text, r.source)


AMBIGUOUS = [
    # (text, reason): found something, but we will not guess
    ("Package Dimensions: 48 x 24 x 6 in", "shipping_size"),
    ("Shipping size 48 x 24 x 6 in", "shipping_size"),
    ('Carton: 50" x 26" x 8"', "shipping_size"),
    ("Mattress size 39 x 75 in", "mattress_size"),
    ("Seat height: 18 in", "component_only"),
    ('Drawer: 12" x 9" x 4"', "component_only"),
    ("Height: 30 in", "incomplete"),
    ('43" Tall Headboard', "incomplete"),
    ("Width: 40 in", "incomplete"),
    ("48 x 24 x 30", "no_unit"),
    ("Width: 20 in Width: 30 in Depth: 10 in", "conflicting_labels"),
    ("5000 x 40 x 30 in", "implausible"),
    ("Width: 39 in to 45 in Depth: 20 in", "range"),
]


@pytest.mark.parametrize(("text", "reason"), AMBIGUOUS)
def test_ambiguous_returns_null_with_reason(text: str, reason: str) -> None:
    r = parse_dimensions(text)
    assert r.status == "ambiguous", r
    assert r.dimensions is None and r.source is None
    assert r.reason == reason


def test_multiple_sizes_is_ambiguous_with_candidates() -> None:
    r = parse_dimensions("Twin (81.4 x 40.1 x 7.9 in), Full (81.4 x 54.3 x 7.9 in)")
    assert r.status == "ambiguous" and r.reason == "multiple_sizes"
    assert r.dimensions is None
    assert r.candidates == [D(w=81.4, d=40.1, h=7.9), D(w=81.4, d=54.3, h=7.9)]


def test_same_size_repeated_is_not_ambiguous() -> None:
    r = parse_dimensions("Twin (81.4 x 40.1 x 7.9 in), Twin XL (81.4 x 40.1 x 7.9 in)")
    assert r.status == "parsed"


def test_shipping_box_does_not_hide_the_real_size() -> None:
    r = parse_dimensions('Desk: 48" x 24" x 30". Package dimensions: 52" x 28" x 6"')
    assert r.status == "parsed" and r.dimensions == D(w=48, d=24, h=30)


MISSING = [
    "",
    "Great desk for your dorm room!",
    "Fits mattress up to 80 in",  # a lone number is not a size
    "Mattress thickness 12 in",
    'Height adjustment from 28.35" to 46.47"',
    "Holds up to 250 lbs. Assembly takes 30 min.",
]


@pytest.mark.parametrize("text", MISSING)
def test_missing(text: str) -> None:
    r = parse_dimensions(text)
    assert r.status == "missing" and r.reason == "no_dimensions"
    assert r.dimensions is None


@pytest.mark.parametrize(
    "text",
    [
        "x x x",
        "1 x",
        "x 2 x",
        '"""',
        "1" * 5000,
        "by by by 5 by",
        "5 x 5 x 5 x 5 x 5 in",
        "\x00\xa0 99 ″",
    ],
)
def test_never_raises(text: str) -> None:
    parse_dimensions(text)


def test_long_adversarial_text_is_fast() -> None:
    import time

    for text in ("1" * 20000, "1 x " * 5000, '1"W ' * 5000, "Width: " * 5000):
        t = time.perf_counter()
        parse_dimensions(text)
        assert time.perf_counter() - t < 2
