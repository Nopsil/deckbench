from sts2sim.engine.seed import canonicalize, warnings


def test_canonicalize_like_game():
    # SeedHelper.CanonicalizeSeed：ToUpperInvariant → O→0 → I→1 → Trim
    assert canonicalize(" ab1oi9 ") == "AB1019"
    assert canonicalize("R5") == "R5"
    assert canonicalize("7F3K9Q2ZB8MA") == "7F3K9Q2ZB8MA"


def test_warnings():
    assert warnings("7F3K9Q2ZB8MA") == []
    assert any("规范化" in w for w in warnings("7f3k9q2zb8ma"))
    assert any("长度" in w for w in warnings("ABC"))
