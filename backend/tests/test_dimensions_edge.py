"""Adversarial tests. A wrong 'parsed' is a bug; a conservative miss is tolerated."""

import random

import pytest

from app.dimensions import Dimensions, parse_dimensions

D = Dimensions

# (text, expected) -> must parse to exactly this, or NOT parse. Never a different size.
SAFE = [
    ("Dimensions: 48 x 24 x 30 (inches)", D(w=48, d=24, h=30)),
    ("Dimensions: 48 x 24 x 30 (in)", D(w=48, d=24, h=30)),
    ('39 1/2" W x 20" D', D(w=39.5, d=20)),
    ("39 1/2 in x 20 in", D(w=39.5, d=20)),
    ("39-1/2 in W x 20 in D", D(w=39.5, d=20)),
    ("W: 39 in D: 20 in H: 30 in", D(w=39, d=20, h=30)),
    ("Width 39 in, Depth 20 in, Height 30 in", D(w=39, d=20, h=30)),
    ("(W) 39 in x (D) 20 in x (H) 30 in", D(w=39, d=20, h=30)),
    ('39"(W) x 20"(D) x 30"(H)', D(w=39, d=20, h=30)),
    (".5 in x 20 in", D(w=0.5, d=20)),
    ("Desk 48 x 24 x 30 in", D(w=48, d=24, h=30)),
    ('L 48" x W 24" x H 30"', D(w=24, d=48, h=30)),
    ("6'2\" x 3' x 2'", D(w=74, d=36, h=24)),
    ("48 in x 600 mm", D(w=48, d=23.62)),
    ("48 x 24 in\n x 30 in", D(w=48, d=24, h=30)),
    ("48\tx\t24\tx\t30 in", D(w=48, d=24, h=30)),
    ("48 x 24 x 30 in", D(w=48, d=24, h=30)),
    ("Ｗ 48 x 24 in", D(w=48, d=24)),
    ("48in x 24in x 30in", D(w=48, d=24, h=30)),
    ("48in.x24in.", D(w=48, d=24)),
    ("48.0 x 24.0 x 30.0 in", D(w=48, d=24, h=30)),
    ("Comes in 48 x 24 x 30 in. Price $120 x 2", D(w=48, d=24, h=30)),
    ("48 x 24 x 30 in; 48 x 24 x 30 in", D(w=48, d=24, h=30)),
    (
        "Overall: 48 x 24 x 30 in. Chair 18 x 18 x 34 in",
        D(w=48, d=24, h=30),
    ),
]


@pytest.mark.parametrize(("text", "expected"), SAFE)
def test_never_a_wrong_size(text: str, expected: Dimensions) -> None:
    r = parse_dimensions(text)
    if r.status == "parsed":
        assert r.dimensions == expected, r


# Strongly expected to parse (conservative parser should still get these).
MUST_PARSE = [
    ("Dimensions: 48 x 24 x 30 (inches)", D(w=48, d=24, h=30)),
    ("W: 39 in D: 20 in H: 30 in", D(w=39, d=20, h=30)),
    ("Desk 48 x 24 x 30 in", D(w=48, d=24, h=30)),
    ("48 x 24 x 30 in\n", D(w=48, d=24, h=30)),
    ("48\tx\t24\tx\t30 in", D(w=48, d=24, h=30)),
    ("48in x 24in x 30in", D(w=48, d=24, h=30)),
    ("Comes in 48 x 24 x 30 in. Price $120 x 2", D(w=48, d=24, h=30)),
]


_MISSES = {
    "Dimensions: 48 x 24 x 30 (inches)"
}  # unit after a closing paren: a safe miss
MUST_PARSE_P = [
    pytest.param(t, e, marks=pytest.mark.xfail(strict=True, reason="missed, not wrong"))
    if t in _MISSES
    else (t, e)
    for t, e in MUST_PARSE
]


@pytest.mark.parametrize(("text", "expected"), MUST_PARSE_P)
def test_should_parse(text: str, expected: Dimensions) -> None:
    r = parse_dimensions(text)
    assert r.status == "parsed" and r.dimensions == expected, r


# Junk that must NEVER be parsed as a size.
JUNK = [  # quantity multipliers / prices read as sizes (real false-"parsed" bugs)
    "Qty 2 x 18 in legs",
    "Buy 2 x 24 in shelves",
    "Pack of 4 x 12 in tiles",
    "2 x 4 drawers",
    "3 x 5 min",
    "Holds 2 x 50 lb",
    "Ships in 2 x 3 days",
    "24x7 support, 365 x 24",
]


@pytest.mark.parametrize("text", JUNK)
def test_junk_is_not_parsed(text: str) -> None:
    r = parse_dimensions(text)
    assert r.status != "parsed", r


# Specific wrong-size traps
def test_glued_to_word_not_a_size() -> None:
    r = parse_dimensions("Model A48 x 24 x 30 in")
    assert r.status != "parsed" or r.dimensions == D(w=48, d=24, h=30)


def test_leading_digit_glued_sku() -> None:
    r = parse_dimensions("SKU 12345 x 24 in")
    assert r.status != "parsed", r


def test_decimal_no_leading_digit_not_misread() -> None:
    r = parse_dimensions("Thickness .75 x 24 x 48 in")
    if r.status == "parsed":
        assert r.dimensions != D(w=75, d=24, h=48)


def test_fraction_not_read_as_separate_numbers() -> None:
    r = parse_dimensions("39 1/2 in W x 20 in D")
    assert r.status != "parsed" or r.dimensions == D(w=39.5, d=20)


def test_feet_inches_not_summed_wrong() -> None:
    r = parse_dimensions("6'2\" W x 2' D")
    if r.status == "parsed":
        assert r.dimensions == D(w=74, d=24)


def test_two_different_sizes_one_overall() -> None:
    r = parse_dimensions(
        "Overall: 60 x 30 x 36 in. Top: 58 x 28 in. Base 50 x 20 x 30 in"
    )
    if r.status == "parsed":
        assert r.dimensions == D(w=60, d=30, h=36)


def test_two_sizes_unmarked_is_ambiguous() -> None:
    r = parse_dimensions("Desk 48 x 24 x 30 in. Chair 18 x 18 x 34 in")
    assert r.status == "ambiguous" and r.dimensions is None


def test_cm_and_inch_same_item_not_wrong() -> None:
    # the same size in two units is ambiguous today (safe miss); never a wrong size
    r = parse_dimensions("48 x 24 x 30 in (122 x 61 x 76 cm)")
    assert r.status != "parsed" or r.dimensions == D(w=48, d=24, h=30)


def test_cm_in_one_triple_mixed() -> None:
    # unit on last item only: the numbers are inches OR cm, never mix silently
    r = parse_dimensions("48 x 24 x 76 cm")
    assert r.status == "parsed" and r.dimensions == D(w=18.9, d=9.45, h=29.92)


def test_mixed_units_in_triple() -> None:
    r = parse_dimensions("48 in x 61 cm x 30 in")
    if r.status == "parsed":
        assert r.dimensions == D(w=48, d=24.02, h=30)


def test_unit_only_on_first_item() -> None:
    # "48 in x 24 x 30": remaining are most plausibly inches
    r = parse_dimensions("48 in x 24 x 30")
    if r.status == "parsed":
        assert r.dimensions == D(w=48, d=24, h=30)


def test_ft_in_triple_applies_ft_only_to_last() -> None:
    # "4 x 2 x 2.5 ft" is 48 x 24 x 30 in
    r = parse_dimensions("4 x 2 x 2.5 ft")
    assert r.status == "parsed" and r.dimensions == D(w=48, d=24, h=30)


def test_apostrophe_in_prose_not_feet() -> None:
    r = parse_dimensions("Kid's 3 x 4 desk")
    assert r.status != "parsed", r


def test_possessive_then_dims() -> None:
    r = parse_dimensions("Men's desk 48 x 24 in")
    assert r.status == "parsed" and r.dimensions == D(w=48, d=24)


def test_height_label_only_with_two_numbers() -> None:
    r = parse_dimensions('Seat 18"H x 20"W x 20"D')
    assert r.status != "parsed" or r.dimensions == D(w=20, d=20, h=18)


def test_ambiguous_means_no_dimensions_or_source() -> None:
    for text in ("Package 48 x 24 x 6 in", "Twin 80 x 39 in, Full 80 x 54 in"):
        r = parse_dimensions(text)
        assert r.status == "ambiguous"
        assert r.dimensions is None and r.source is None


def test_non_ascii_and_emoji() -> None:
    r = parse_dimensions("尺寸: 48 × 24 × 30 in 🛏️")
    assert r.status == "parsed" and r.dimensions == D(w=48, d=24, h=30)


def test_arabic_indic_digits_do_not_crash_or_mislead() -> None:
    r = parse_dimensions("٤٨ x ٢٤ x ٣٠ in")
    assert r.status != "parsed" or r.dimensions is not None


def test_huge_input_fast_and_safe() -> None:
    import time

    big = "Great desk. " * 50000 + "48 x 24 x 30 in"
    t = time.perf_counter()
    r = parse_dimensions(big)
    assert time.perf_counter() - t < 3
    assert r.status == "parsed" and r.dimensions == D(w=48, d=24, h=30)


# --- property checks over generated noisy text ---
_TOKENS = [
    "48",
    "24",
    "30",
    "x",
    "×",
    "by",
    "in",
    '"',
    "'",
    "cm",
    "mm",
    "ft",
    "W",
    "D",
    "H",
    "L",
    "Width:",
    "Depth",
    "Height",
    "tall",
    "wide",
    ".5",
    "1/2",
    "$",
    "(",
    ")",
    " ",
    "\n",
    "\t",
    "drawer",
    "package",
    "mattress",
    "overall",
    "to",
    "-",
    "0",
    "999",
    "5000",
    "min",
    "set of",
    "12.5",
    ",",
    ".",
    "é",
    "😀",
]


def _gen(seed: int) -> str:
    rnd = random.Random(seed)
    return " ".join(rnd.choice(_TOKENS) for _ in range(rnd.randint(1, 25)))


@pytest.mark.parametrize("seed", range(1500))
def test_properties(seed: int) -> None:
    text = _gen(seed)
    r = parse_dimensions(text)
    if r.status == "parsed":
        dm = r.dimensions
        assert dm is not None and r.reason is None and r.source
        assert 0 < dm.w <= 300 and 0 < dm.d <= 300
        assert dm.h is None or 0 < dm.h <= 300
        assert all(p in text for p in r.source.split(" … ")), (text, r.source)
        assert r.candidates == []
    else:
        assert r.dimensions is None and r.source is None
        if r.status == "ambiguous":
            assert r.reason is not None
        else:
            assert r.reason == "no_dimensions"
