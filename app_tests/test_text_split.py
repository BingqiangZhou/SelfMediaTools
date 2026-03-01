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

