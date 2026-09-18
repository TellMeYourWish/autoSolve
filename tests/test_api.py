import base64
from io import BytesIO
from pathlib import Path

from fontTools.ttLib import TTFont

from app import create_app
from autosolve.providers import StaticSolverProvider


def client():
    app = create_app(StaticSolverProvider("A"))
    app.config.update(TESTING=True)
    return app.test_client()


def test_normalize_question_and_options():
    response = client().post("/api/v1/normalize", json={
        "question": "【单选题】1. <b>下面哪项正确？</b>",
        "type": "单选题",
        "options": ["A. 甲", "B. 乙"],
    })
    assert response.status_code == 200
    assert response.json["question"] == "下面哪项正确？"
    assert response.json["question_type"] == 0
    assert response.json["options"] == ["甲", "乙"]


def test_solve_json_uses_standard_envelope():
    response = client().post("/api/v1/solve", json={
        "question": "1. 下面哪项正确？",
        "type": 0,
        "options": ["A. 甲", "B. 乙"],
    })
    assert response.status_code == 200
    assert response.json["code"] == 1
    assert response.json["data"][0]["answer"] == "A"
    assert response.json["interface"] == "native"
    assert response.json["normalized"]["options"] == ["甲", "乙"]


def test_legacy_form_endpoint_is_compatible():
    response = client().post("/api/search.php", data={
        "question": "判断题：地球是圆的。",
        "type": "判断题",
        "options": '["对", "错"]',
    })
    assert response.status_code == 200
    assert response.json["data"][0]["answer"] == "A"
    assert response.json["normalized"]["question_type"] == 3
    assert response.json["interface"] == "ocs"


def test_ocs_endpoint_accepts_exact_userscript_payload():
    response = client().post(
        "/api/ocs/solve",
        json={
            "title": "1. 下面哪项正确？",
            "type": "single",
            "options": "A. 甲\nB. 乙",
            "interface": "ocs",
        },
    )
    assert response.status_code == 200
    assert response.json["interface"] == "ocs"
    assert response.json["data"][0]["answer"] == "A"
    assert response.json["data"][0]["question"] == "下面哪项正确？"
    assert response.json["normalized"]["question_type"] == 0
    assert response.json["normalized"]["options"] == ["甲", "乙"]


def test_ocs_endpoint_accepts_json_without_content_type():
    response = client().post(
        "/api/ocs/solve",
        data='{"title":"地球是圆的。","type":"judgement","options":["对","错"]}',
    )
    assert response.status_code == 200
    assert response.json["normalized"]["question_type"] == 3


def test_native_endpoint_can_select_ocs_interface():
    response = client().post(
        "/api/v1/solve?interface=ocs",
        json={"question": "测试", "type": "single", "options": ["甲", "乙"]},
    )
    assert response.status_code == 200
    assert response.json["interface"] == "ocs"


def test_invalid_interface_is_rejected():
    response = client().post(
        "/api/v1/solve",
        json={"question": "测试", "interface": "bad"},
    )
    assert response.status_code == 400
    assert "interface" in response.json["msg"]


def test_empty_question_is_rejected():
    response = client().post("/api/v1/solve", json={"type": 0})
    assert response.status_code == 400
    assert response.json["code"] == 0


def test_diagnostics_endpoint_reports_injected_provider():
    response = client().get("/api/v1/diagnostics")
    assert response.status_code == 200
    assert response.json["provider"] == "StaticSolverProvider"
    assert response.json["interfaces"]["ocs"] == "/api/ocs/solve"
    assert response.json["interfaces"]["ocs_font_decode"] == "/api/ocs/font/decode"
    assert response.json["font_decoder"]["algorithm"] == "anti-spider-font-glyf-v1"


def test_ocs_font_decode_uses_local_glyph_fingerprints():
    raw_font = (Path(__file__).parents[2] / "anti-spider-font" / "aa.ttf").read_bytes()
    codepoints = sorted((TTFont(BytesIO(raw_font)).getBestCmap() or {}).keys())
    response = client().post(
        "/api/ocs/font/decode",
        json={
            "font_base64": base64.b64encode(raw_font).decode("ascii"),
            "used_codepoints": codepoints,
        },
    )
    assert response.status_code == 200
    assert response.json["code"] == 1
    assert response.json["data"]["complete"] is True
    assert response.json["data"]["unresolved_codepoints"] == []
    assert len(response.json["data"]["mappings"]) == len(codepoints)


def test_session_id_is_preserved_in_normalized_payload():
    response = client().post("/api/v1/normalize", json={
        "question": "单选题：测试",
        "type": 0,
        "options": ["甲", "乙"],
        "session_id": "course-1-lesson-2",
    })
    assert response.status_code == 200
    assert response.json["session_id"] == "course-1-lesson-2"


def test_disabled_provider_mode_returns_503(monkeypatch):
    monkeypatch.setenv("AUTOSOLVE_PROVIDER", "disabled")
    app = create_app()
    app.config.update(TESTING=True)

    response = app.test_client().post(
        "/api/v1/solve",
        json={"question": "test", "type": "single", "options": ["A", "B"]},
    )

    assert response.status_code == 503
    assert response.json["error"] == "provider_not_configured"


def test_deepseek_provider_mode_can_be_selected(monkeypatch):
    monkeypatch.setenv("AUTOSOLVE_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")
    app = create_app()
    app.config.update(TESTING=True)

    response = app.test_client().get("/api/v1/diagnostics")

    assert response.status_code == 200
    assert response.json["provider"] == "DeepSeekApiProvider"
