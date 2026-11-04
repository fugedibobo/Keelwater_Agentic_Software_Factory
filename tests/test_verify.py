import pytest

from signal_engine.verify import verify_quote

T = "So um, we upload documents one at a time and it's “very” slow — honestly £1,250.50 a month is fine."
FS = 'x\nClaim > Documents: click "Document type" select, rage x5\ny'

CASES = [
    ("exact", "we upload documents one at a time", "gong", T, "exact"),
    ("curly quotes and dash", 'it\'s "very" slow - honestly', "gong", T, "normalised"),
    ("case fold", "WE UPLOAD DOCUMENTS ONE AT A TIME", "intercom", T, "normalised"),
    ("filler in text dropped (gong)", "So we upload documents one at a time", "gong", T, "normalised"),
    ("filler in text kept (intercom)", "So we upload documents one at a time", "intercom", T, "failed"),
    ("filler in quote dropped (fireflies)", "we um upload documents one at a time", "fireflies", T, "normalised"),
    ("punctuation removed", "documents, one at a time; and it's very slow", "gong", T, "normalised"),
    ("apostrophe kept in word", "and it’s very slow honestly", "intercom", T, "normalised"),
    ("digit separators kept", "honestly £1,250.50 a month is fine", "intercom", T, "exact"),
    ("digit separators differ", "honestly £125050 a month is fine", "intercom", T, "failed"),
    ("whitespace collapsed", "we upload   documents\none at a time", "intercom", T, "normalised"),
    ("nbsp", "one at a time and it's very slow", "intercom", T, "normalised"),
    ("nfkc ligature", "ﬁle documents one at a time", "intercom", "we file documents one at a time", "normalised"),
    ("ellipsis in order", "we upload documents ... it's very slow ... honestly", "intercom", T, "normalised"),
    ("ellipsis exact in order", "we upload documents ... one at a time and", "intercom", T, "exact"),
    ("ellipsis out of order", "it's very slow ... we upload documents one", "intercom", T, "failed"),
    ("ellipsis char, short fragments ignored", "we upload documents one at a time … so … very slow", "intercom", T, "exact"),
    ("under 5 words", "one at a time", "intercom", T, "failed"),
    ("over 60 words", " ".join(["word"] * 61), "intercom", " ".join(["word"] * 61), "failed"),
    ("5 words ok", "one at a time and", "intercom", T, "exact"),
    ("fullstory exact", 'Claim > Documents: click "Document type" select, rage x5', "fullstory", FS, "exact"),
    ("fullstory never normalised", "claim documents click document type select rage x5", "fullstory", FS, "failed"),
]


@pytest.mark.parametrize("name,quote,source,text,want", CASES, ids=[c[0] for c in CASES])
def test_verify_quote(name, quote, source, text, want):
    assert verify_quote(quote, text, source)[0] == want


def test_quote_only_in_context_text_fails():
    # callers pass the snippet's own text only; words that live in context_text are not found
    assert verify_quote("please tell us what is slow for you", T, "gong") == ("failed", None, None)


def test_exact_span_slices_back_to_the_quote():
    q = "documents one at a time"
    m, s, e = verify_quote(q, T, "gong")
    assert (m, T[s:e]) == ("exact", q)


def test_normalised_span_covers_original_words():
    m, s, e = verify_quote("we UPLOAD documents one at a time and it's very slow", T, "gong")
    assert m == "normalised" and T[s:e] == "we upload documents one at a time and it's “very” slow"
    assert verify_quote("So we upload documents one at a time", T, "gong")[1:] == (0, T.index("time") + 4)
