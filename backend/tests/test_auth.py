import pytest
import uuid
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.api.main import app
from backend.database import get_db, SessionLocal
from backend.models.user import User
from backend.models.case import Case
from backend.models.audit_log import AuditLog
from backend.models.revoked_token import RevokedToken
from backend.services.auth_service import hash_password, create_access_token, create_refresh_token, decode_token, _ip_attempts
from backend.config import settings

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def reset_ip_rate_limiter():
    """Reset the in-memory IP rate limiter and unlock test accounts before every test."""
    _ip_attempts.clear()
    # Ensure test accounts are unlocked between tests
    db = SessionLocal()
    try:
        for email in [
            "test_adjuster_a@claimlens.internal",
            "test_adjuster_b@claimlens.internal",
            "test_supervisor@claimlens.internal",
            "test_admin@claimlens.internal",
        ]:
            u = db.query(User).filter(User.email == email).first()
            if u:
                u.failed_attempts = 0
                u.locked_until = None
        db.commit()
    finally:
        db.close()
    yield
    _ip_attempts.clear()


@pytest.fixture(scope="module")
def db_session():
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture(scope="module", autouse=True)
def setup_test_users(db_session: Session):
    """Ensures test users exist in the database."""
    users_data = [
        {"email": "test_adjuster_a@claimlens.internal", "role": "adjuster", "name": "Adjuster A"},
        {"email": "test_adjuster_b@claimlens.internal", "role": "adjuster", "name": "Adjuster B"},
        {"email": "test_supervisor@claimlens.internal", "role": "supervisor", "name": "Test Supervisor"},
        {"email": "test_admin@claimlens.internal", "role": "admin", "name": "Test Admin"},
    ]
    for u in users_data:
        existing = db_session.query(User).filter(User.email == u["email"]).first()
        if not existing:
            new_u = User(
                full_name=u["name"],
                email=u["email"],
                password_hash=hash_password("StrongPassword123!"),
                role=u["role"],
                is_active=True
            )
            db_session.add(new_u)
        else:
            existing.password_hash = hash_password("StrongPassword123!")
            existing.is_active = True
            existing.failed_attempts = 0
            existing.locked_until = None
    db_session.commit()


def _make_client():
    """Returns a fresh TestClient that persists cookies across requests."""
    return TestClient(app, raise_server_exceptions=False)


def test_login_success():
    """Test successful login sets cookies and returns CSRF token in body."""
    auth_client = _make_client()
    resp = auth_client.post("/api/auth/login", json={
        "email": "test_adjuster_a@claimlens.internal",
        "password": "StrongPassword123!"
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "success"
    assert data["user"]["email"] == "test_adjuster_a@claimlens.internal"
    assert data["user"]["role"] == "adjuster"
    # CSRF token is returned in body AND cookie
    assert data.get("csrf_token") is not None
    # access_token and refresh_token are HttpOnly — present in client cookie jar
    assert "access_token" in auth_client.cookies
    assert "refresh_token" in auth_client.cookies


def test_login_wrong_password():
    """Test login with wrong password returns generic 401 error."""
    resp = client.post("/api/auth/login", json={
        "email": "test_adjuster_a@claimlens.internal",
        "password": "IncorrectPassword999!"
    })
    assert resp.status_code == 401
    assert "Incorrect email or password" in resp.json()["detail"]


def test_lockout_after_repeated_failures(db_session: Session):
    """Test 5th failed attempt triggers lockout and returns 403."""
    email = "lockout_victim@claimlens.internal"
    existing = db_session.query(User).filter(User.email == email).first()
    if not existing:
        db_session.add(User(
            full_name="Victim User",
            email=email,
            password_hash=hash_password("ValidPassword123!"),
            role="adjuster",
            is_active=True
        ))
        db_session.commit()

    # Reset attempts
    db_session.expire_all()
    victim = db_session.query(User).filter(User.email == email).first()
    victim.failed_attempts = 0
    victim.locked_until = None
    db_session.commit()

    # Attempts 1-4 should all return 401
    for i in range(4):
        r = client.post("/api/auth/login", json={"email": email, "password": "BadPassword1!"})
        assert r.status_code == 401, f"Expected 401 on attempt {i+1}, got {r.status_code}"

    # 5th attempt triggers lockout — expect 403
    r5 = client.post("/api/auth/login", json={"email": email, "password": "BadPassword1!"})
    assert r5.status_code == 403, f"Expected 403 on 5th attempt (lockout), got {r5.status_code}: {r5.text}"
    assert "locked" in r5.json()["detail"].lower()

    # 6th attempt (correct or wrong) still locked
    r6 = client.post("/api/auth/login", json={"email": email, "password": "ValidPassword123!"})
    assert r6.status_code == 403
    assert "locked" in r6.json()["detail"].lower()


def test_unauthenticated_access_denied_401():
    """Test endpoints reject unauthenticated requests with 401."""
    clean_client = _make_client()
    resp = clean_client.get("/api/cases")
    assert resp.status_code == 401
    assert "Authentication required" in resp.json()["detail"]


def test_role_based_access_control_403():
    """Test non-admin (adjuster) cannot access admin endpoints."""
    adj_client = _make_client()
    adj_client.post("/api/auth/login", json={
        "email": "test_adjuster_a@claimlens.internal",
        "password": "StrongPassword123!"
    })
    admin_resp = adj_client.get("/api/admin/users")
    assert admin_resp.status_code == 403
    assert "Access denied" in admin_resp.json()["detail"]


def test_adjuster_case_isolation_403(db_session: Session):
    """Adjuster A cannot see or access Adjuster B's case."""
    db_session.expire_all()
    adj_a = db_session.query(User).filter(User.email == "test_adjuster_a@claimlens.internal").first()
    adj_b = db_session.query(User).filter(User.email == "test_adjuster_b@claimlens.internal").first()

    # Create case owned by Adjuster B
    case_b = Case(
        id=str(uuid.uuid4()),
        claim_number=f"CLM-{uuid.uuid4().hex[:6].upper()}",
        policy_number="POL-SECRET-001",
        claimant_name="Alice Isolated",
        creator_id=adj_b.id,
        status="Pending human review"
    )
    db_session.add(case_b)
    db_session.commit()

    # Login as Adjuster A
    client_a = _make_client()
    client_a.post("/api/auth/login", json={
        "email": "test_adjuster_a@claimlens.internal",
        "password": "StrongPassword123!"
    })

    # Adjuster A tries to GET Adjuster B's case → 403
    resp_get = client_a.get(f"/api/cases/{case_b.id}")
    assert resp_get.status_code == 403
    assert "Forbidden" in resp_get.json()["detail"]

    # Adjuster A's case list should NOT include Adjuster B's case
    resp_list = client_a.get("/api/cases")
    assert resp_list.status_code == 200
    case_ids = [c["id"] for c in resp_list.json()]
    assert case_b.id not in case_ids

    # Supervisor CAN see Adjuster B's case
    client_sup = _make_client()
    client_sup.post("/api/auth/login", json={
        "email": "test_supervisor@claimlens.internal",
        "password": "StrongPassword123!"
    })
    resp_sup_get = client_sup.get(f"/api/cases/{case_b.id}")
    assert resp_sup_get.status_code == 200
    assert resp_sup_get.json()["case"]["claimant_name"] == "Alice Isolated"


def test_token_expiry_and_refresh():
    """Test token refresh rotates the refresh token and extends session."""
    auth_client = _make_client()
    login_resp = auth_client.post("/api/auth/login", json={
        "email": "test_supervisor@claimlens.internal",
        "password": "StrongPassword123!"
    })
    assert login_resp.status_code == 200
    first_refresh = auth_client.cookies.get("refresh_token")
    assert first_refresh is not None, "Login must set refresh_token cookie"

    # Call refresh — cookie jar forwards refresh_token automatically
    refresh_resp = auth_client.post("/api/auth/refresh")
    assert refresh_resp.status_code == 200, f"Refresh failed: {refresh_resp.text}"
    assert refresh_resp.json()["status"] == "refreshed"

    second_refresh = auth_client.cookies.get("refresh_token")
    assert second_refresh is not None
    assert second_refresh != first_refresh, "Refresh token MUST be rotated on each refresh"


def test_logout_invalidates_session(db_session: Session):
    """Test logout clears cookies and blacklists the refresh token."""
    auth_client = _make_client()
    login_resp = auth_client.post("/api/auth/login", json={
        "email": "test_admin@claimlens.internal",
        "password": "StrongPassword123!"
    })
    assert login_resp.status_code == 200
    refresh_tok = auth_client.cookies.get("refresh_token")
    assert refresh_tok is not None, "Login must set refresh_token cookie"

    # Logout
    logout_resp = auth_client.post("/api/auth/logout")
    assert logout_resp.status_code == 200

    # Verify the refresh token was revoked in DB
    payload = decode_token(refresh_tok)
    assert payload is not None, "Refresh token should decode correctly before revocation check"
    jti = payload.get("jti")
    assert jti is not None
    db_session.expire_all()
    revoked = db_session.query(RevokedToken).filter(RevokedToken.jti == jti).first()
    assert revoked is not None, "Refresh token JTI must be in revoked_tokens table after logout"

    # Manually inject revoked token back and verify refresh is denied
    auth_client.cookies.set("refresh_token", refresh_tok)
    bad_refresh = auth_client.post("/api/auth/refresh")
    assert bad_refresh.status_code == 401


def test_audit_log_records_user_on_decision(db_session: Session):
    """Adjuster decision audit entry must record user_id and user_role."""
    adj_client = _make_client()
    login_resp = adj_client.post("/api/auth/login", json={
        "email": "test_adjuster_a@claimlens.internal",
        "password": "StrongPassword123!"
    })
    assert login_resp.status_code == 200
    # CSRF token is returned in the response body
    csrf_token = login_resp.json().get("csrf_token")
    assert csrf_token, "Login response must include csrf_token in body"

    db_session.expire_all()
    adj_user = db_session.query(User).filter(User.email == "test_adjuster_a@claimlens.internal").first()

    # Create a case
    create_resp = adj_client.post(
        "/api/cases",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "policy_number": "POL-AUDIT-TEST",
            "claimant_name": "Audit Test Claimant"
        }
    )
    assert create_resp.status_code == 200, f"Case creation failed: {create_resp.text}"
    case_id = create_resp.json()["id"]

    # Submit decision
    dec_resp = adj_client.post(
        f"/api/cases/{case_id}/decision",
        headers={"X-CSRF-Token": csrf_token},
        json={
            "decision": "Approved",
            "reason": "Clear evidence alignment and consistent repair estimates confirmed."
        }
    )
    assert dec_resp.status_code == 200, f"Decision failed: {dec_resp.text}"

    # Check audit log
    db_session.expire_all()
    decision_log = db_session.query(AuditLog).filter(
        AuditLog.case_id == case_id,
        AuditLog.event_type == "adjuster_decision"
    ).first()

    assert decision_log is not None
    assert decision_log.user_id == adj_user.id
    assert decision_log.user_role == "adjuster"
    assert decision_log.decision == "Approved"
    assert "Clear evidence alignment" in decision_log.reason


def test_csrf_protection_on_mutations():
    """State-changing requests authenticated by cookie but missing CSRF header must return 403."""
    auth_client = _make_client()
    auth_client.post("/api/auth/login", json={
        "email": "test_adjuster_a@claimlens.internal",
        "password": "StrongPassword123!"
    })
    # POST without X-CSRF-Token header (cookie is present so CSRF applies)
    resp = auth_client.post("/api/cases", json={
        "policy_number": "POL-CSRF-FAIL",
        "claimant_name": "Should Fail"
    })
    assert resp.status_code == 403, f"Expected 403 CSRF failure, got {resp.status_code}: {resp.text}"
    assert "CSRF validation failed" in resp.json()["detail"]


def test_password_strength_enforcement():
    """Password validator rejects short or common passwords."""
    auth_client = _make_client()
    login_resp = auth_client.post("/api/auth/login", json={
        "email": "test_adjuster_a@claimlens.internal",
        "password": "StrongPassword123!"
    })
    assert login_resp.status_code == 200
    csrf = login_resp.json().get("csrf_token")
    assert csrf, "CSRF token required from login"

    # Too short
    r_short = auth_client.post(
        "/api/auth/change-password",
        headers={"X-CSRF-Token": csrf},
        json={"current_password": "StrongPassword123!", "new_password": "short"}
    )
    assert r_short.status_code == 400
    assert "at least 10 characters" in r_short.json()["detail"]

    # Common password
    r_common = auth_client.post(
        "/api/auth/change-password",
        headers={"X-CSRF-Token": csrf},
        json={"current_password": "StrongPassword123!", "new_password": "password12345"}
    )
    assert r_common.status_code == 400
    assert "too common" in r_common.json()["detail"]
