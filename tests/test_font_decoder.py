import base64
from io import BytesIO
from pathlib import Path

from fontTools.ttLib import TTFont

from autosolve.font_decoder import ChaoxingFontDecoder, FontDecodeError


FIXTURE_FONT = Path(__file__).parents[2] / "anti-spider-font" / "aa.ttf"


def _fixture_payload() -> tuple[str, list[int]]:
    raw_font = FIXTURE_FONT.read_bytes()
    # Keep default lazy loading: the production glyph fingerprint needs raw data.
    codepoints = sorted((TTFont(BytesIO(raw_font)).getBestCmap() or {}).keys())
    return base64.b64encode(raw_font).decode("ascii"), codepoints


def test_decoder_covers_all_fixture_font_codepoints():
    font_base64, codepoints = _fixture_payload()
    decoder = ChaoxingFontDecoder()

    first = decoder.decode(font_base64, codepoints)
    second = decoder.decode(font_base64, codepoints)

    assert first.complete
    assert first.unresolved_codepoints == ()
    assert len(first.used_font_codepoints) == len(first.mappings)
    assert len(first.mappings) > 0
    assert second.cache_hit is True


def test_decoder_rejects_malformed_payload():
    decoder = ChaoxingFontDecoder()
    try:
        decoder.decode("not base64", [])
    except FontDecodeError as exc:
        assert "font_base64" in str(exc)
    else:
        raise AssertionError("malformed payload must not be accepted")
