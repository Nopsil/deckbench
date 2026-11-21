"""可玩角色名单来自生成代码给出的模型，不把没出现的角色写死进名单。"""
import os
import sys

from sts2sim.engine.characters import map_from_models

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))


class _Iron:
    _cs_name = "Ironclad"
    IsPlayable = True


class _Fool:
    _cs_name = "Fool"
    IsPlayable = True


class _Mock:
    _cs_name = "Deprived"
    IsPlayable = False


def test_models_keep_playable_names_and_drop_unplayable():
    got = map_from_models([_Iron(), _Fool(), _Mock()], lambda: {"should": object})
    assert list(got) == ["Ironclad", "Fool"]
    assert got["Fool"] is _Fool


def test_empty_models_use_the_fallback():
    sentinel = {"Ironclad": _Iron}
    assert map_from_models(None, lambda: sentinel) is sentinel
    assert map_from_models([], lambda: sentinel) is sentinel


def test_unreadable_models_use_the_fallback():
    assert map_from_models(object(), lambda: {"Ironclad": _Iron}) == {"Ironclad": _Iron}


def test_deck_card_goto_patch_keeps_the_result_body():
    """补丁只拆掉跳转阶梯。结果仍要构造并返回，不能把方法后半段吞掉。"""
    import cs_patches

    src = (
        "\t\tdeckCard?.AssertMutable();\n"
        "\t\tif (deckCard == null)\n"
        "\t\t{\n"
        "\t\t\tgoto IL_0025;\n"
        "\t\t}\n"
        "\t\tCardPile pile = deckCard.Pile;\n"
        "\t\tif (pile != null)\n"
        "\t\t{\n"
        "\t\t\tPileType type = pile.Type;\n"
        "\t\t\tif (type == PileType.Deck)\n"
        "\t\t\t{\n"
        "\t\t\t\tgoto IL_0025;\n"
        "\t\t\t}\n"
        "\t\t}\n"
        "\t\tbool flag = true;\n"
        "\t\tgoto IL_0027;\n"
        "\t\tIL_0027:\n"
        "\t\tif (flag)\n"
        "\t\t{\n"
        "\t\t\tthrow new InvalidOperationException(\"Card must be in a deck!\");\n"
        "\t\t}\n"
        "\t\treturn obj;\n"
        "\t\tIL_0025:\n"
        "\t\tflag = false;\n"
        "\t\tgoto IL_0027;\n"
    )
    out = cs_patches.apply_patches("GameActions/PlayerChoiceResult.cs", src)
    assert "goto IL_0025" not in out
    assert "return obj;" in out
    assert "deckCard != null && (deckCard.Pile == null || deckCard.Pile.Type != PileType.Deck)" in out
    assert "InvalidOperationException" in out
