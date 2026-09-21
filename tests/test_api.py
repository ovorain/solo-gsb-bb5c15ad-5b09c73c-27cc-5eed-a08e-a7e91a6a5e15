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
    # Hall 违例证书：孤立评审人 r2 自身构成缺口 1 的子集。
    witness = data["hall_witness"]
    assert witness == {
        "reviewer_ids": ["r2"],
        "neighboring_manuscript_ids": [],
        "deficiency": 1,
    }
    # 绝不返回部分成功标记。
    assert "assignment" not in data


def test_409_hall_witness_multiple_gaps():
    """多缺口：r1、r2、r3 都只允许同一篇稿件 m1，缺口为 2。

    r0->m0 为链外强制边；m1 只能服务三人之一，故最大匹配基数 2，
    两侧各有 2 人未匹配，证书 deficiency=2。
    """
    resp = client.post(
        "/audit",
        json={
            "reviewers": ["r0", "r1", "r2", "r3"],
            "manuscripts": ["m0", "m1", "m2", "m3"],
            "allowed_pairings": [
                {"reviewer_id": "r0", "manuscript_id": "m0"},
                {"reviewer_id": "r1", "manuscript_id": "m1"},
                {"reviewer_id": "r2", "manuscript_id": "m1"},
                {"reviewer_id": "r3", "manuscript_id": "m1"},
            ],
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert len(data["maximum_matching"]) == 2
    assert len(data["unmatched_reviewer_ids"]) == 2
    assert data["unmatched_manuscript_ids"] == ["m2", "m3"]

    witness = data["hall_witness"]
    assert witness["reviewer_ids"] == ["r1", "r2", "r3"]
    assert witness["neighboring_manuscript_ids"] == ["m1"]
    assert witness["deficiency"] == 2
    # deficiency 等于全局未匹配人数（两侧）。
    assert witness["deficiency"] == len(data["unmatched_reviewer_ids"])
    assert witness["deficiency"] == len(data["unmatched_manuscript_ids"])
    # 链外的 r0/m0 不参与证书。
    assert "r0" not in witness["reviewer_ids"]
    assert "m0" not in witness["neighboring_manuscript_ids"]


def test_409_hall_witness_nonobvious_subset():
    """非显然 Hall 子集：违例集合经交替链把已匹配评审人卷入。

    边：
      r0 -> m1
      r1 -> m0, m1
      r2 -> m0, m1
      r3 -> m2            （安全匹配，不参与证书）

    确定性最大匹配（null 字典序最小）：r0 可保持未匹配（r1、r2 仍能
    覆盖 m0、m1），故未匹配评审人为 r0，匹配为 r1->m0、r2->m1、r3->m2；
    未匹配稿件为 m3。
    从未匹配的 r0 出发：非匹配边 r0->m1，匹配边 m1->r2，
    再经非匹配边 r2->m0、匹配边 m0->r1，r1 的非匹配边回到 m1。
    故违例子集为 {r0, r1, r2}，其在原图中的全部邻居恰为 {m0, m1}，
    缺口 3-2=1；注意被匹配上的 r1、r2 也被交替路径卷入。
    """
    resp = client.post(
        "/audit",
        json={
            "reviewers": ["r0", "r1", "r2", "r3"],
            "manuscripts": ["m0", "m1", "m2", "m3"],
            "allowed_pairings": [
                {"reviewer_id": "r0", "manuscript_id": "m1"},
                {"reviewer_id": "r1", "manuscript_id": "m0"},
                {"reviewer_id": "r1", "manuscript_id": "m1"},
                {"reviewer_id": "r2", "manuscript_id": "m0"},
                {"reviewer_id": "r2", "manuscript_id": "m1"},
                {"reviewer_id": "r3", "manuscript_id": "m2"},
            ],
        },
    )
    assert resp.status_code == 409, resp.text
    data = resp.json()
    assert len(data["maximum_matching"]) == 3
    witness = data["hall_witness"]
    assert witness["reviewer_ids"] == ["r0", "r1", "r2"]
    assert witness["neighboring_manuscript_ids"] == ["m0", "m1"]
    assert witness["deficiency"] == 1
    assert witness["deficiency"] == len(data["unmatched_reviewer_ids"])
    # r3/m2 是链外安全匹配，不出现在证书中。
    assert "r3" not in witness["reviewer_ids"]
    assert "m2" not in witness["neighboring_manuscript_ids"]


def test_409_hall_witness_stable_regardless_of_input_order():
    """打乱 reviewers/manuscripts/pairings 的输入顺序，证书完全一致。"""
    pairings = [
        {"reviewer_id": "r3", "manuscript_id": "m2"},
        {"reviewer_id": "r2", "manuscript_id": "m1"},
        {"reviewer_id": "r2", "manuscript_id": "m0"},
        {"reviewer_id": "r1", "manuscript_id": "m1"},
        {"reviewer_id": "r1", "manuscript_id": "m0"},
        {"reviewer_id": "r0", "manuscript_id": "m1"},
    ]
    resp_a = client.post(
        "/audit",
        json={
            "reviewers": ["r0", "r1", "r2", "r3"],
            "manuscripts": ["m0", "m1", "m2", "m3"],
            "allowed_pairings": pairings,
        },
    )
    resp_b = client.post(
        "/audit",
        json={
            "reviewers": ["r3", "r1", "r0", "r2"],
            "manuscripts": ["m2", "m0", "m3", "m1"],
            "allowed_pairings": list(reversed(pairings)),
        },
    )
    assert resp_a.status_code == resp_b.status_code == 409
    assert resp_a.json()["hall_witness"] == resp_b.json()["hall_witness"]
    witness = resp_a.json()["hall_witness"]
    assert witness["reviewer_ids"] == sorted(witness["reviewer_ids"])
    assert witness["neighboring_manuscript_ids"] == sorted(
        witness["neighboring_manuscript_ids"]
    )


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
