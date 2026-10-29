"""Python port of engine.js (run only, no solver). Standard library only.

Kept line-for-line with engine.js so scripts/check_engine.py can compare the two. Same seeded
generator (mulberry32), same Box-Muller draw, same path rules. All values are real.
"""
import json, math
from pathlib import Path

M32 = 0xFFFFFFFF

DEFAULTS = dict(age=32, retire=50, until=95, balance=150000, contrib=40000, spend=60000,
                mode="historical", sims=5000, seed=2026, block=10, stock=75, glide=False,
                stockAtRetire=50, rule="constant", rate=4, floor=75, ceiling=150,
                pension=0, pensionAge=67, muS=None, sdS=None)


def load_returns(path=None):
    path = path or Path(__file__).resolve().parent.parent / "data" / "returns.json"
    return json.loads(Path(path).read_text())


def rng(seed):
    state = [seed & M32]

    def imul(a, b):
        return (a * b) & M32

    def nxt():
        state[0] = (state[0] + 0x6D2B79F5) & M32
        t = state[0]
        t = imul(t ^ (t >> 15), t | 1)
        t ^= (t + imul(t ^ (t >> 7), t | 61)) & M32
        return ((t ^ (t >> 14)) & M32) / 4294967296
    return nxt


def normal(r):
    u = v = 0.0
    while u == 0:
        u = r()
    while v == 0:
        v = r()
    return math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * v)


def fill(p):
    o = dict(DEFAULTS)
    o.update({k: v for k, v in p.items() if v is not None})
    return o


def mean_sd(xs):
    n = len(xs)
    m = sum(xs) / n
    return m, math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def corr(a, b):
    ma, sa = mean_sd(a)
    mb, sb = mean_sd(b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (len(a) - 1) / (sa * sb)


def share_at(p, y, W):
    if not p["glide"]:
        return p["stock"] / 100
    if y > W or W <= 1:
        return p["stockAtRetire"] / 100
    return (p["stock"] + (p["stockAtRetire"] - p["stock"]) * (y - 1) / (W - 1)) / 100


def play_path(p, rs, rb, T, W):
    """Returns (balances 0..T, fail_age or 0, end balance, min spending, avg spending)."""
    b = p["balance"]
    fail_age = 0
    spend = p["spend"]
    C = spend
    iwr = 0.0
    min_c, sum_c, n_c = math.inf, 0.0, 0
    lo, hi = p["floor"] / 100 * spend, p["ceiling"] / 100 * spend
    bal = [0.0] * (T + 1)
    bal[0] = b
    for y in range(1, T + 1):
        age = p["age"] + y
        w = share_at(p, y, W)
        r = w * rs[y - 1] + (1 - w) * rb[y - 1]
        if y <= W:
            b = b * (1 + r) + p["contrib"]
        else:
            pen = p["pension"] if age >= p["pensionAge"] else 0
            if fail_age:
                bal[y] = 0
                continue
            if p["rule"] == "percent":
                C = min(max(p["rate"] / 100 * b + pen, lo), hi)
            elif p["rule"] == "guardrails":
                if y == W + 1:
                    C = spend
                    iwr = spend / b if b > 0 else math.inf
                else:
                    wr = C / b if b > 0 else math.inf
                    left = T - y + 1
                    if wr > iwr * 1.2 and left > 15:
                        C *= 0.9
                    elif wr < iwr * 0.8:
                        C *= 1.1
                    C = min(max(C, lo), hi)
            else:
                C = spend
            min_c = min(min_c, C)
            sum_c += C
            n_c += 1
            wd = max(0.0, C - pen)
            if wd > b:
                b = 0
                fail_age = age
                bal[y] = 0
                continue
            b = (b - wd) * (1 + r)
        bal[y] = b
    return bal, fail_age, b, (min_c if n_c else spend), (sum_c / n_c if n_c else spend)


def historical(p, D):
    T = p["until"] - p["age"]
    W = max(0, min(T, p["retire"] - p["age"]))
    years = D["year"]
    first, last = years[0], years[-1]
    wins = []
    for Ry in range(first + W, last + 1):
        start = Ry - W - first
        avail = min(T, len(years) - start)
        rs = [D["stock"][start + y] if y < avail else 0 for y in range(T)]
        rb = [D["bond"][start + y] if y < avail else 0 for y in range(T)]
        bal, fail_age, end, min_c, avg_c = play_path(p, rs, rb, avail, W)
        wins.append(dict(year=Ry, complete=avail == T, failAge=fail_age, end=end, minC=min_c, avgC=avg_c,
                         atRet=bal[min(W, avail)]))
    done = [w for w in wins if w["complete"]]
    ok = sum(1 for w in done if not w["failAge"])
    return dict(mode="historical", rate=ok / len(done) if done else float("nan"), n=len(done), windows=wins,
                medEnd=quant(sorted(w["end"] for w in done), 0.5) if done else None)


def montecarlo(p, D):
    T = p["until"] - p["age"]
    W = max(0, min(T, p["retire"] - p["age"]))
    N, r, L = p["sims"], rng(p["seed"]), len(D["year"])
    ms, ss = mean_sd(D["stock"])
    mb, sb = mean_sd(D["bond"])
    rho = corr(D["stock"], D["bond"])
    muS = ms if p["muS"] is None else p["muS"] / 100
    sdS = ss if p["sdS"] is None else p["sdS"] / 100
    k2 = math.sqrt(1 - rho * rho)
    blk = max(1, round(p["block"]))
    ok, ends = 0, []
    for _ in range(N):
        rs, rb = [0.0] * T, [0.0] * T
        if p["mode"] == "normal":
            for y in range(T):
                z1, z2 = normal(r), normal(r)
                rs[y] = max(-0.99, muS + sdS * z1)
                rb[y] = max(-0.99, mb + sb * (rho * z1 + k2 * z2))
        else:
            y = 0
            while y < T:
                st = math.floor(r() * L)
                j = 0
                while j < blk and y < T:
                    ix = (st + j) % L
                    rs[y], rb[y] = D["stock"][ix], D["bond"][ix]
                    j += 1
                    y += 1
        _, fail_age, end, _, _ = play_path(p, rs, rb, T, W)
        ok += 0 if fail_age else 1
        ends.append(end)
    return dict(mode=p["mode"], rate=ok / N, n=N, medEnd=quant(sorted(ends), 0.5))


def quant(sorted_xs, f):
    return sorted_xs[min(len(sorted_xs) - 1, math.floor(f * (len(sorted_xs) - 1)))]


def run(params, D):
    p = fill(params)
    return historical(p, D) if p["mode"] == "historical" else montecarlo(p, D)
