import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import get_settings
from app.core.moderation import check_prompt_safety

client = TestClient(app)
settings = get_settings()

def test_health():
    response = client.get("/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "uptime_seconds" in data

def test_config():
    response = client.get("/v1/config")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert "fast" in data["models"]
    assert "quality" in data["models"]
    assert len(data["aspect_ratios"]) >= 5
    assert len(data["styles"]) >= 6

def test_moderation_engine():
    # Valid creative prompts
    safe, err = check_prompt_safety("A majestic cyberpunk dragon flying over neon Tokyo")
    assert safe is True
    assert err is None

    safe, err = check_prompt_safety("Oil painting of a calm rainy mountain forest")
    assert safe is True

    # Empty prompt
    safe, err = check_prompt_safety("   ")
    assert safe is False
    assert "empty" in err.lower()

    # Policy violations
    safe, err = check_prompt_safety("underage nude teenager")
    assert safe is False
    assert "safety guidelines" in err

    safe, err = check_prompt_safety("extreme torture murder decapitat scene")
    assert safe is False

def test_credits_endpoint():
    # With DEV_BYPASS_AUTH=True (or default dev headers)
    settings.DEV_BYPASS_AUTH = True
    response = client.get("/v1/credits", headers={"Authorization": "Bearer dev-token"})
    assert response.status_code == 200
    data = response.json()
    assert "balance" in data
    assert data["balance"] >= 0
    assert "max_daily_generations" in data

def test_generation_endpoint_flow():
    settings.DEV_BYPASS_AUTH = True
    payload = {
        "prompt": "A serene lotus pond in twilight with bioluminescent koi fish",
        "model": "fast",
        "aspect_ratio": "1:1",
        "style": "fantasy"
    }
    response = client.post(
        "/v1/generations",
        json=payload,
        headers={"Authorization": "Bearer dev-token"}
    )
    assert response.status_code == 200
    assert response.headers.get("content-type") in ["image/webp", "image/jpeg"]
    assert "x-generation-id" in response.headers
    assert len(response.content) > 0

def test_report_endpoint():
    settings.DEV_BYPASS_AUTH = True
    payload = {
        "reason": "violence_harm",
        "details": "Test report details"
    }
    response = client.post(
        "/v1/reports",
        json=payload,
        headers={"Authorization": "Bearer dev-token"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "received"
    assert "report_id" in data

def test_claim_reward():
    settings.DEV_BYPASS_AUTH = True
    # Initial balance check
    init_res = client.get("/v1/credits", headers={"Authorization": "Bearer dev-token"})
    assert init_res.status_code == 200
    init_balance = init_res.json()["balance"]

    response = client.post("/v1/rewards/claim", headers={"Authorization": "Bearer dev-token"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["balance"] == init_balance + 1

def test_grant_welcome_bonus():
    settings.DEV_BYPASS_AUTH = True
    response = client.post("/v1/credits/grant-welcome", headers={"Authorization": "Bearer dev-token"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "balance" in data

