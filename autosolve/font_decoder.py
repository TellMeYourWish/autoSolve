from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import pickle
from collections import OrderedDict
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from fontTools.ttLib import TTFont, TTLibError

logger = logging.getLogger(__name__)


class FontDecodeError(ValueError):
    """The Chaoxing secret font cannot be decoded safely."""


@dataclass(frozen=True, slots=True)
class FontDecodeResult:
    font_id: str
    mappings: dict[int, int]
    font_codepoints: frozenset[int]
    used_font_codepoints: tuple[int, ...]
    unresolved_codepoints: tuple[int, ...]
    cache_hit: bool

    @property
    def complete(self) -> bool:
        return not self.unresolved_codepoints


@dataclass(frozen=True, slots=True)
class _FontMapping:
    mappings: dict[int, int]
    font_codepoints: frozenset[int]


class ChaoxingFontDecoder:
    """Decode Chaoxing subset fonts with the local anti-spider glyph corpus.

    The anti-spider corpus identifies a glyph from the raw ``glyf`` bytes.  Do
    not use ``TTFont(..., lazy=False)`` here: eager loading decompiles glyphs
    and discards the raw bytes used by the fingerprint algorithm.
    """

    MAX_FONT_BYTES = 2 * 1024 * 1024
    MAX_USED_CODEPOINTS = 4096
    CACHE_SIZE = 32

    def __init__(self, asset_dir: Path | None = None) -> None:
        self.asset_dir = asset_dir or Path(__file__).with_name("assets") / "chaoxing_font"
        self._glyph_hash_to_name, self._glyph_name_to_codepoint = self._load_assets()
        self._cache: OrderedDict[str, _FontMapping] = OrderedDict()

    def diagnostics(self) -> dict[str, Any]:
        return {
            "algorithm": "anti-spider-font-glyf-v1",
            "asset_dir": str(self.asset_dir),
            "glyph_fingerprints": len(self._glyph_hash_to_name),
            "reference_cjk_codepoints": len(self._glyph_name_to_codepoint),
            "cached_fonts": len(self._cache),
        }

    def decode(self, font_base64: str, used_codepoints: list[int] | tuple[int, ...]) -> FontDecodeResult:
        logger.info(
            "chaoxing font decode input payload_chars=%s used_codepoints=%s",
            len(font_base64) if isinstance(font_base64, str) else "invalid",
            len(used_codepoints) if isinstance(used_codepoints, (list, tuple)) else "invalid",
        )
        if not isinstance(font_base64, str) or not font_base64.strip():
            raise FontDecodeError("font_base64 is required")
        if not isinstance(used_codepoints, (list, tuple)):
            raise FontDecodeError("used_codepoints must be an array")
        if len(used_codepoints) > self.MAX_USED_CODEPOINTS:
            raise FontDecodeError("too many used codepoints")

        try:
            raw_font = base64.b64decode(font_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise FontDecodeError("font_base64 is invalid") from exc
        if not raw_font or len(raw_font) > self.MAX_FONT_BYTES:
            raise FontDecodeError("font payload size is invalid")

        used = self._normalize_codepoints(used_codepoints)
        font_id = hashlib.sha256(raw_font).hexdigest()
        cached = self._cache.get(font_id)
        cache_hit = cached is not None
        if cached is None:
            cached = self._build_mapping(raw_font)
            self._cache[font_id] = cached
            self._cache.move_to_end(font_id)
            while len(self._cache) > self.CACHE_SIZE:
                self._cache.popitem(last=False)
        else:
            self._cache.move_to_end(font_id)

        used_font_codepoints = tuple(sorted(used & cached.font_codepoints))
        unresolved = tuple(codepoint for codepoint in used_font_codepoints if codepoint not in cached.mappings)
        logger.info(
            "chaoxing font decode result font_id=%s cmap_codepoints=%s used_in_font=%s mapped=%s unresolved=%s cache_hit=%s",
            font_id[:12],
            len(cached.font_codepoints),
            len(used_font_codepoints),
            len(cached.mappings),
            len(unresolved),
            cache_hit,
        )
        return FontDecodeResult(
            font_id=font_id,
            mappings=cached.mappings,
            font_codepoints=cached.font_codepoints,
            used_font_codepoints=used_font_codepoints,
            unresolved_codepoints=unresolved,
            cache_hit=cache_hit,
        )

    def _load_assets(self) -> tuple[dict[tuple[bytes, bytes], str], dict[str, int]]:
        glyph_path = self.asset_dir / "HanSansCN_glyfHashedTables.pkl"
        cmap_path = self.asset_dir / "HanSansCN_CmapTables.pkl"
        try:
            with glyph_path.open("rb") as file:
                glyph_rows = pickle.load(file)[0]
            with cmap_path.open("rb") as file:
                cmap_rows = pickle.load(file)
        except (OSError, pickle.UnpicklingError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Chaoxing font assets are unavailable: {exc}") from exc

        glyph_hash_to_name = {fingerprint: glyph_name for glyph_name, fingerprint in glyph_rows}
        glyph_name_to_codepoint = {
            glyph_name: codepoint
            for codepoint, glyph_name in cmap_rows
            if 0x4E00 <= codepoint <= 0x9FA5
        }
        if not glyph_hash_to_name or not glyph_name_to_codepoint:
            raise RuntimeError("Chaoxing font assets are empty")
        return glyph_hash_to_name, glyph_name_to_codepoint

    def _build_mapping(self, raw_font: bytes) -> _FontMapping:
        try:
            font = TTFont(BytesIO(raw_font))
            glyphs = font["glyf"].glyphs
            cmap = font.getBestCmap() or {}
        except (TTLibError, KeyError, AttributeError) as exc:
            raise FontDecodeError("unsupported Chaoxing font") from exc

        source_codepoint_by_glyph = {glyph_name: codepoint for codepoint, glyph_name in cmap.items()}
        mappings: dict[int, int] = {}
        for glyph_name, glyph in glyphs.items():
            source_codepoint = source_codepoint_by_glyph.get(glyph_name)
            raw_glyph = getattr(glyph, "data", None)
            if source_codepoint is None or raw_glyph is None:
                continue
            fingerprint = (hashlib.sha1(raw_glyph).digest(), hashlib.md5(raw_glyph).digest())
            reference_glyph = self._glyph_hash_to_name.get(fingerprint)
            target_codepoint = self._glyph_name_to_codepoint.get(reference_glyph)
            if target_codepoint is not None:
                mappings[source_codepoint] = target_codepoint

        return _FontMapping(mappings=mappings, font_codepoints=frozenset(cmap))

    @staticmethod
    def _normalize_codepoints(values: list[int] | tuple[int, ...]) -> set[int]:
        normalized: set[int] = set()
        for value in values:
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0x10FFFF:
                raise FontDecodeError("used_codepoints contains an invalid codepoint")
            normalized.add(value)
        return normalized
