from text_split import split_sentences


def test_split_punctuation_and_newline() -> None:
    text = "\u7b2c\u4e00\u53e5\u3002\u7b2c\u4e8c\u53e5\uff1f\uff01\n\u7b2c\u4e09\u6bb5\u6ca1\u6709\u53e5\u53f7\n\uff01\uff01\n"
    assert split_sentences(text) == [
        "\u7b2c\u4e00\u53e5\u3002",
        "\u7b2c\u4e8c\u53e5\uff1f\uff01",
        "\u7b2c\u4e09\u6bb5\u6ca1\u6709\u53e5\u53f7",
    ]


def test_split_keeps_punctuation_clusters() -> None:
    text = "\u4f60\u597d\uff01\uff01\u6211\u5f88\u597d\u2026\u2026\u4f60\u5462?"
    assert split_sentences(text) == [
        "\u4f60\u597d\uff01\uff01",
        "\u6211\u5f88\u597d\u2026\u2026",
        "\u4f60\u5462?",
    ]


def test_split_does_not_break_decimals_or_commas() -> None:
    text = "\u4eca\u5929\u80a1\u4ef7\u4e0a\u6da83.5%\uff0c\u4f46\u660e\u5929\u53ef\u80fd\u56de\u8c03\u3002"
    assert split_sentences(text) == [
        "\u4eca\u5929\u80a1\u4ef7\u4e0a\u6da83.5%\uff0c\u4f46\u660e\u5929\u53ef\u80fd\u56de\u8c03\u3002",
    ]


def test_split_does_not_break_english_abbreviation_dots() -> None:
    text = "Version 3.14 is stable, e.g. use it."
    assert split_sentences(text) == ["Version 3.14 is stable, e.g. use it."]

