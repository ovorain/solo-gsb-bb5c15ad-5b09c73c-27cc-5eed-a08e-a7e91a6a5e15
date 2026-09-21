"""API 层测试：200 / 409 / 422 及错误定位。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def payload(**overrides):
    base = {
        "reviewers": ["r0", "r1", "r2"],
        "manuscripts": ["m0", "m1", "m2"],
        "allowed_pairings": [
            {"reviewer_id": "r0", "manuscript_id": "m0"},
            {"reviewer_id": "r0", "manuscript_id": "m1"},
            {"reviewer_id": "r1", "manuscript_id": "m0"},
            {"reviewer_id": "r1", "manuscript_id": "m1"},
            {"reviewer_id": "r2", "manuscript_id": "m2"},
        ],
    }
    base.update(overrides)
    return base


def test_success_200():
    resp = client.post("/audit", json=payload())
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["perfect_match_exists"] is True
    assignment = data["assignment"]
    assert [a["reviewer_id"] for a in assignment] == ["r0", "r1", "r2"]
    by_r = {a["reviewer_id"]: a for a in assignment}
    assert by_r["r0"]["manuscript_id"] == "m0"
    assert by_r["r0"]["forced"] is False
    alt = by_r["r0"]["alternative"]
    assert {p["reviewer_id"]: p["manuscript_id"] for p in alt} == {
        "r0": "m1",
        "r1": "m0",
        "r2": "m2",
    }
    assert by_r["r2"]["forced"] is True
    assert by_r["r2"]["alternative"] is None


def test_no_perfect_match_409():
    # r2 没有任何允许配对 => 最大匹配基数为 2。
    resp = client.post(
        "/audit",
        json=payload(
            allowed_pairings=[
                {"reviewer_id": "r0", "manuscript_id": "m0"},
                {"reviewer_id": "r1", "manuscript_id": "m1"},
            ]
        ),
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert data["perfect_match_exists"] is False
    assert len(data["maximum_matching"]) == 2
    assert data["unmatched_reviewer_ids"] == ["r2"]
    assert data["unmatched_manuscript_ids"] == ["m2"]
    # 绝不返回部分成功标记。
    assert "assignment" not in data


def test_duplicate_reviewer_422_locates_index():
    resp = client.post(
        "/audit", json=payload(reviewers=["r0", "r1", "r0"])
    )
    assert resp.status_code == 422
    locs = [tuple(e["loc"]) for e in resp.json()["detail"]]
    assert ("body", "reviewers", 2) in locs


def test_duplicate_manuscript_422():
    resp = client.post("/audit", json=payload(manuscripts=["m0", "m1", "m1"]))
    assert resp.status_code == 422
    locs = [tuple(e["loc"]) for e in resp.json()["detail"]]
    assert ("body", "manuscripts", 2) in locs


def test_count_mismatch_422():
    resp = client.post(
        "/audit",
        json=payload(
            reviewers=["r0", "r1"],
            manuscripts=["m0"],
            allowed_pairings=[{"reviewer_id": "r0", "manuscript_id": "m0"}],
        ),
    )
    assert resp.status_code == 422
    locs = [tuple(e["loc"]) for e in resp.json()["detail"]]
    assert ("body", "manuscripts") in locs


def test_duplicate_pairing_422():
    pairings = payload()["allowed_pairings"] + [
        {"reviewer_id": "r0", "manuscript_id": "m0"}
    ]
    resp = client.post("/audit", json=payload(allowed_pairings=pairings))
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail[-1]["loc"] == ["body", "allowed_pairings", 5]
    assert detail[-1]["type"] == "duplicate_pairing"


def test_unknown_references_422():
    resp = client.post(
        "/audit",
        json=payload(
            allowed_pairings=[
                {"reviewer_id": "ghost", "manuscript_id": "m0"},
                {"reviewer_id": "r0", "manuscript_id": "ghost-m"},
            ]
        ),
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    locs = {tuple(e["loc"]) for e in detail}
    assert ("body", "allowed_pairings", 0, "reviewer_id") in locs
    assert ("body", "allowed_pairings", 1, "manuscript_id") in locs


def test_empty_lists_422():
    resp = client.post(
        "/audit",
        json={"reviewers": [], "manuscripts": [], "allowed_pairings": []},
    )
    assert resp.status_code == 422


def test_empty_string_id_422():
    resp = client.post(
        "/audit",
        json=payload(
            allowed_pairings=[{"reviewer_id": "r0", "manuscript_id": "  "}]
        ),
    )
    assert resp.status_code == 422


def test_extra_field_422():
    resp = client.post(
        "/audit",
        json=payload(
            allowed_pairings=[
                {"reviewer_id": "r0", "manuscript_id": "m0", "weight": 1}
            ]
        ),
    )
    assert resp.status_code == 422
