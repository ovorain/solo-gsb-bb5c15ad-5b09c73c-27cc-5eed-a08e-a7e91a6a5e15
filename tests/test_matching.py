"""核心算法测试：以全排列暴力枚举交叉验证字典序、强制性与最大匹配。"""

import itertools

import pytest

from app.matching import run_audit


def all_perfect_matchings(reviewers, manuscripts, edges):
    """暴力枚举所有完美匹配，返回按评审人排序的 (rid -> mid) 元组集合。"""
    adj = {r: [] for r in reviewers}
    for r, m in edges:
        adj[r].append(m)
    results = set()
    for perm in itertools.permutations(sorted(manuscripts)):
        mapping = dict(zip(sorted(reviewers), perm))
        if all(mapping[r] in adj[r] for r in sorted(reviewers)):
            results.add(tuple(mapping[r] for r in sorted(reviewers)))
    return results


def all_matchings(reviewers, manuscripts, edges, size):
    """暴力枚举指定基数的全部匹配（用 reviewer 子集 × 分配）。"""
    adj = {r: [m for m in manuscripts if (r, m) in edges] for r in reviewers}
    out = []
    for k in range(size, len(reviewers) + 1):
        for subset in itertools.combinations(sorted(reviewers), k):
            for chosen in itertools.permutations(sorted(manuscripts), k):
                if all(chosen[i] in adj[r] for i, r in enumerate(subset)):
                    out.append((subset, chosen))
    return out


def lex_key(seq):
    """未匹配记 None，None 小于任何字符串（用标签元组避免 None/str 比较）。"""
    return tuple((0, "") if m is None else (1, m) for m in seq)


@pytest.mark.parametrize("seed", range(200))
def test_audit_matches_bruteforce(seed):
    import random

    rng = random.Random(seed)
    n = rng.randint(1, 4)
    reviewers = [f"r{i}" for i in range(n)]
    manuscripts = [f"m{i}" for i in range(n)]
    all_edges = [(r, m) for r in reviewers for m in manuscripts]
    k = rng.randint(1, len(all_edges))
    edges = rng.sample(all_edges, k)

    result = run_audit(reviewers, manuscripts, edges)
    perfects = all_perfect_matchings(reviewers, manuscripts, edges)

    if not perfects:
        assert result.perfect_match_exists is False
        assert len(result.pairs) == result.max_matching_size
        # 未匹配数量两侧相等且互补。
        assert len(result.unmatched_reviewers) == n - result.max_matching_size
        assert len(result.unmatched_manuscripts) == n - result.max_matching_size
        matched_r = {r for r, _ in result.pairs}
        matched_m = {m for _, m in result.pairs}
        assert result.unmatched_reviewers == sorted(set(reviewers) - matched_r)
        assert result.unmatched_manuscripts == sorted(set(manuscripts) - matched_m)
        # 不存在更大匹配（暴力：该基数下没有更大基数的匹配）。
        assert not all_matchings(
            reviewers, manuscripts, edges, result.max_matching_size + 1
        )
        # 确定性匹配本身合法。
        assert all((r, m) in edges for r, m in result.pairs)
        # 确定性：与字典序最小的 null-aware 最大匹配一致。
        canon = lex_smallest_bruteforce(reviewers, manuscripts, edges, perfects)
        assert sorted(result.pairs) == sorted(canon)

        check_hall_witness(result, reviewers, manuscripts, edges)
        return

    assert result.perfect_match_exists is True
    assert result.max_matching_size == n
    assert result.hall_witness is None

    sorted_r = sorted(reviewers)
    canonical = min(perfects, key=lex_key)
    got = {r: (m, forced, alt) for r, m, forced, alt in result.pairs}

    for index, reviewer in enumerate(sorted_r):
        manuscript, forced, alternative = got[reviewer]
        assert manuscript == canonical[index]

        # 强制：每个完美匹配都含此边。
        truly_forced = all(p[index] == manuscript for p in perfects)
        assert forced is truly_forced

        if not forced:
            assert alternative is not None
            alt_map = dict(alternative)
            assert len(alternative) == n
            # 替代分配完整、合法、且不含被审计边。
            assert alt_map[reviewer] != manuscript
            alt_tuple = tuple(alt_map[r] for r in sorted_r)
            assert alt_tuple in perfects

    # 排序：输出按评审人 ID 升序。
    assert [r for r, *_ in result.pairs] == sorted_r


def lex_smallest_bruteforce(reviewers, manuscripts, edges, perfects):
    """暴力求字典序最小（None 最小）的最大基数匹配，作为 409 对照。"""
    if perfects:
        return list(zip(sorted(reviewers), min(perfects)))

    adj = {r: {m for m in manuscripts if (r, m) in edges} for r in reviewers}
    m_sorted = sorted(manuscripts)
    r_sorted = sorted(reviewers)

    def gen(i, used, chosen):
        if i == len(r_sorted):
            yield tuple(chosen)
            return
        yield from gen(i + 1, used, chosen + [None])
        for m in m_sorted:
            if m not in used and m in adj[r_sorted[i]]:
                yield from gen(i + 1, used | {m}, chosen + [m])

    candidates = list(gen(0, set(), []))
    max_card = max(sum(m is not None for m in seq) for seq in candidates)
    best_seq = min(
        (seq for seq in candidates if sum(m is not None for m in seq) == max_card),
        key=lex_key,
    )
    return [(r, m) for r, m in zip(r_sorted, best_seq) if m is not None]


def check_hall_witness(result, reviewers, manuscripts, edges):
    """校验 409 的 Hall 违例证书：邻居精确性、缺口、排序及 Hall 最优性。"""
    witness = result.hall_witness
    assert witness is not None

    rids = witness.reviewer_ids
    mids = witness.neighboring_manuscript_ids

    # 列表排序且无重复。
    assert rids == sorted(set(rids))
    assert mids == sorted(set(mids))
    # 证书中的评审人与稿件均为合法引用。
    assert set(rids) <= set(reviewers)
    assert set(mids) <= set(manuscripts)
    # 违例子集必须非空（无完美匹配时 Hall 必有违例）。
    assert rids

    # 稿件集合恰为这些评审人在**原 allowed_pairings** 中的全部邻居。
    adj = {r: set() for r in reviewers}
    for r, m in edges:
        adj[r].add(m)
    true_neighbors = set().union(*(adj[r] for r in rids))
    assert set(mids) == true_neighbors

    # deficiency = 评审人数 - 邻居数 = 全局未匹配人数（两侧相等）。
    assert witness.deficiency == len(rids) - len(mids)
    assert witness.deficiency == len(result.unmatched_reviewers)
    assert witness.deficiency == len(result.unmatched_manuscripts)
    assert witness.deficiency >= 1

    # Hall 最优性（暴力）：该子集缺口不小于任何评审人子集的缺口，
    # 且恰为 n - 最大匹配基数；n ≤ 4，枚举全部 2^n 子集。
    max_gap = 0
    for k in range(len(reviewers) + 1):
        for subset in itertools.combinations(sorted(reviewers), k):
            neighbors = {m for r in subset for m in adj[r]}
            max_gap = max(max_gap, len(subset) - len(neighbors))
    assert max_gap == witness.deficiency


def test_hall_witness_multiple_gaps():
    """算法层：3 名评审人共享 1 篇稿件，缺口为 2；链外强制边不卷入。"""
    reviewers = ["r0", "r1", "r2", "r3"]
    manuscripts = ["m0", "m1", "m2", "m3"]
    edges = [
        ("r0", "m0"),
        ("r1", "m1"),
        ("r2", "m1"),
        ("r3", "m1"),
    ]
    result = run_audit(reviewers, manuscripts, edges)
    assert result.perfect_match_exists is False
    assert result.max_matching_size == 2
    witness = result.hall_witness
    assert witness.reviewer_ids == ["r1", "r2", "r3"]
    assert witness.neighboring_manuscript_ids == ["m1"]
    assert witness.deficiency == 2


def test_hall_witness_nonobvious_alternating_chain():
    """算法层：证书经交替链包含已匹配评审人（非显然子集）。"""
    reviewers = ["r0", "r1", "r2", "r3"]
    manuscripts = ["m0", "m1", "m2", "m3"]
    edges = [
        ("r0", "m1"),
        ("r1", "m0"),
        ("r1", "m1"),
        ("r2", "m0"),
        ("r2", "m1"),
        ("r3", "m2"),
    ]
    result = run_audit(reviewers, manuscripts, edges)
    assert result.perfect_match_exists is False
    witness = result.hall_witness
    assert witness.reviewer_ids == ["r0", "r1", "r2"]
    assert witness.neighboring_manuscript_ids == ["m0", "m1"]
    assert witness.deficiency == 1
    assert result.unmatched_reviewers == ["r0"]
    assert result.unmatched_manuscripts == ["m3"]


def test_known_forced_edges():
    """经典例：r2/m2 为强制边；r0、r1 可互换。"""
    reviewers = ["r0", "r1", "r2"]
    manuscripts = ["m0", "m1", "m2"]
    edges = [("r0", "m0"), ("r0", "m1"), ("r1", "m0"), ("r1", "m1"), ("r2", "m2")]
    result = run_audit(reviewers, manuscripts, edges)
    assert result.perfect_match_exists is True
    by_r = {r: (m, forced) for r, m, forced, _ in result.pairs}
    assert by_r["r0"] == ("m0", False)
    assert by_r["r1"] == ("m1", False)
    assert by_r["r2"] == ("m2", True)
