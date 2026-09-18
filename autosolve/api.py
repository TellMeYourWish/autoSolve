from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict
from typing import Any

from flask import Blueprint, jsonify, request

from .font_decoder import ChaoxingFontDecoder, FontDecodeError
from .models import QuestionRequest
from .normalizer import normalize_request
from .services import SolverService

logger = logging.getLogger(__name__)

INTERFACE_NATIVE = "native"
INTERFACE_OCS = "ocs"
SUPPORTED_INTERFACES = (INTERFACE_NATIVE, INTERFACE_OCS)


def _decode_options(value: Any) -> list[str]:
    """Accept native arrays plus the formats commonly emitted by OCS wrappers."""
    if value is None or value == "":
        return []
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    if not isinstance(value, str):
        raise ValueError("options 必须是字符串数组、JSON 数组或换行分隔文本")

    stripped = value.strip()
    if not stripped:
        return []
    try:
        decoded = json.loads(stripped)
    except json.JSONDecodeError:
        decoded = None
    if isinstance(decoded, list) and all(isinstance(item, str) for item in decoded):
        return decoded
    return [item.strip() for item in stripped.splitlines() if item.strip()]


def _payload() -> dict[str, Any]:
    if request.is_json:
        return request.get_json(silent=True) or {}

    # Some userscript managers send JSON without a Content-Type header.
    raw_body = request.get_data(cache=True, as_text=True).strip()
    if raw_body:
        try:
            decoded = json.loads(raw_body)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, dict):
            return decoded

    return {
        "question": request.form.get("question") or request.form.get("title", ""),
        "type": request.form.get("type"),
        "options": _decode_options(request.form.get("options", "")),
        "metadata": {"session_id": request.form.get("session_id")},
        "interface": request.form.get("interface"),
    }


def _request_from_payload(data: dict[str, Any]) -> QuestionRequest:
    question = data.get("question") or data.get("title") or data.get("stem") or ""
    options = _decode_options(data.get("options"))
    metadata = data.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError("metadata 必须是对象")
    metadata = dict(metadata)
    if data.get("session_id") is not None:
        metadata["session_id"] = data.get("session_id")
    metadata.setdefault("interface", data.get("interface"))
    return QuestionRequest(
        question=str(question),
        question_type=data.get("question_type", data.get("type")),
        options=options,
        metadata=metadata,
    )


def _success(normalized: Any, solution: Any, interface: str) -> dict[str, Any]:
    return {
        "code": 1,
        "msg": "success",
        "data": [{
            "answer": solution.answer,
            "question": normalized.question if interface == INTERFACE_OCS else solution.answer,
            "question_type": normalized.question_type,
            "confidence": solution.confidence,
            "explanation": solution.explanation,
        }],
        "interface": interface,
        "normalized": asdict(normalized),
        "quota_info": None,
        "request_id": uuid.uuid4().hex,
    }


def build_api_blueprint(
    service: SolverService, font_decoder: ChaoxingFontDecoder | None = None
) -> Blueprint:
    api = Blueprint("api", __name__)
    decoder = font_decoder or ChaoxingFontDecoder()

    @api.before_request
    def log_request():
        if (
            request.path.endswith("/solve")
            or request.path.endswith("/search.php")
            or request.path.endswith("/font/decode")
        ):
            logger.info("request method=%s path=%s content_type=%s", request.method, request.path, request.content_type)

    @api.post("/api/v1/normalize")
    def normalize():
        try:
            result = normalize_request(_request_from_payload(_payload()))
            return jsonify(asdict(result))
        except (TypeError, ValueError) as exc:
            return jsonify({"code": 0, "msg": str(exc)}), 400

    def solve_with_interface(default_interface: str):
        request_id = uuid.uuid4().hex
        try:
            data = _payload()
            interface = str(
                request.args.get("interface") or data.get("interface") or default_interface
            ).strip().lower()
            if interface not in SUPPORTED_INTERFACES:
                raise ValueError(
                    f"interface 必须是 {INTERFACE_NATIVE} 或 {INTERFACE_OCS}"
                )
            normalized, solution = service.solve(_request_from_payload(data))
            result = _success(normalized, solution, interface)
            result["request_id"] = request_id
            logger.info(
                "solve success request_id=%s interface=%s type=%s",
                request_id,
                interface,
                normalized.question_type,
            )
            return jsonify(result)
        except NotImplementedError as exc:
            logger.warning("provider not configured request_id=%s", request_id)
            return jsonify({"code": 0, "msg": str(exc), "error": "provider_not_configured", "request_id": request_id}), 503
        except (TypeError, ValueError) as exc:
            logger.warning("bad request request_id=%s error=%s", request_id, exc)
            return jsonify({"code": 0, "msg": str(exc), "request_id": request_id}), 400
        except Exception as exc:
            logger.exception("provider error request_id=%s", request_id)
            result = {"code": 0, "msg": "解题 provider 执行失败", "error": "provider_error", "request_id": request_id}
            if request.args.get("debug") == "1":
                result["debug"] = {"exception": type(exc).__name__, "detail": str(exc)}
            return jsonify(result), 502

    @api.post("/api/v1/solve")
    def solve():
        return solve_with_interface(INTERFACE_NATIVE)

    @api.post("/api/ocs/solve")
    def ocs_solve():
        return solve_with_interface(INTERFACE_OCS)

    @api.post("/api/ocs/font/decode")
    def decode_chaoxing_font():
        """Decode only the encrypted codepoints actually used by an OCS page."""
        request_id = uuid.uuid4().hex
        try:
            data = _payload()
            font_base64 = data.get("font_base64", "")
            used_codepoints = data.get("used_codepoints", [])
            logger.info(
                "font decode received request_id=%s payload_chars=%s used_codepoints=%s",
                request_id,
                len(font_base64) if isinstance(font_base64, str) else "invalid",
                len(used_codepoints) if isinstance(used_codepoints, list) else "invalid",
            )
            result = decoder.decode(
                font_base64,
                used_codepoints,
            )
            if not result.complete:
                logger.warning(
                    "font decode incomplete request_id=%s font_id=%s unresolved=%s",
                    request_id,
                    result.font_id[:12],
                    len(result.unresolved_codepoints),
                )
                return jsonify({
                    "code": 0,
                    "msg": "Chaoxing font contains unresolved glyphs",
                    "error": "font_decode_incomplete",
                    "request_id": request_id,
                    "data": {
                        "font_id": result.font_id,
                        "unresolved_codepoints": list(result.unresolved_codepoints),
                        "complete": False,
                    },
                }), 422

            logger.info(
                "font decode success request_id=%s font_id=%s mapped=%s cache_hit=%s",
                request_id,
                result.font_id[:12],
                len(result.mappings),
                result.cache_hit,
            )
            return jsonify({
                "code": 1,
                "msg": "success",
                "request_id": request_id,
                "data": {
                    "font_id": result.font_id,
                    "mappings": {str(source): target for source, target in result.mappings.items()},
                    "used_font_codepoints": list(result.used_font_codepoints),
                    "unresolved_codepoints": [],
                    "complete": True,
                    "cache_hit": result.cache_hit,
                },
            })
        except FontDecodeError as exc:
            logger.warning("font decode rejected request_id=%s error=%s", request_id, exc)
            return jsonify({
                "code": 0,
                "msg": str(exc),
                "error": "font_decode_invalid",
                "request_id": request_id,
            }), 400
        except Exception:
            logger.exception("font decode failed request_id=%s", request_id)
            return jsonify({
                "code": 0,
                "msg": "font decoder failed",
                "error": "font_decode_failed",
                "request_id": request_id,
            }), 500

    @api.get("/api/v1/diagnostics")
    def diagnostics():
        provider = service.provider
        if hasattr(provider, "diagnostics"):
            provider_info: Any = provider.diagnostics()
        else:
            provider_info = type(provider).__name__
        return jsonify({
            "status": "ok",
            "provider": provider_info,
            "interfaces": {
                "native": "/api/v1/solve",
                "ocs": "/api/ocs/solve",
                "legacy_ocs": "/api/search.php",
                "ocs_font_decode": "/api/ocs/font/decode",
            },
            "font_decoder": decoder.diagnostics(),
        })

    # 兼容题库脚本原来的 POST /api/search.php 表单参数。
    @api.post("/api/search.php")
    def legacy_search():
        return solve_with_interface(INTERFACE_OCS)

    return api
