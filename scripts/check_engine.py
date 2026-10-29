"""Check the engine from the command line.

    python3 scripts/check_engine.py           # Python port only
    python3 scripts/check_engine.py --js      # also run engine.js in headless Chromium (needs playwright)

1. Benchmarks: the 4% rule over 30 years with historical rolling windows, against the
   Trinity study (Cooley, Hubbard and Walz 1998: 95% at 50/50, 98% at 75/25, retirement years
   1926-1966) and Bengen's 1994 worst-case withdrawal rate of 4.15%.
2. The default plan in all three modes, the spending rules and block lengths, for the write-up.
3. With --js, the same cases through engine.js, which must match the Python port.

Writes data/validation.json and exits non-zero on a mismatch or a benchmark far off.
"""
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
D = engine.load_returns()

RETIREE = dict(mode="historical", age=65, retire=65, until=95, balance=1_000_000, contrib=0, spend=40_000)


def window_rate(res, lo=None, hi=None):
    w = [x for x in res["windows"] if x["complete"] and (lo is None or x["year"] >= lo) and (hi is None or x["year"] <= hi)]
    return sum(1 for x in w if not x["failAge"]) / len(w), len(w), [x["year"] for x in w if x["failAge"]]


def damodaran_series():
    path = Path.home() / "data-cache" / "fire-retirement-simulator" / "histretSP.xls"
    try:
        import xlrd
        sh = xlrd.open_workbook(path).sheet_by_name("Nominal vs Real Data")
    except Exception:
        return None
    yrs, st, bd = [], [], []
    for i in range(1, sh.nrows):
        y = sh.cell_value(i, 0)
        if isinstance(y, float) and isinstance(sh.cell_value(i, 5), float):
            yrs.append(int(y)); st.append(sh.cell_value(i, 5)); bd.append(sh.cell_value(i, 7))
    return dict(year=yrs, stock=st, bond=bd)


def safemax(stock, lo=None, hi=None):
    """Highest initial withdrawal rate (to 0.01%) that survives every complete 30-year window."""
    a, b = 1.0, 10.0
    while b - a > 0.005:
        m = (a + b) / 2
        r = engine.run(dict(RETIREE, stock=stock, spend=m * 10_000), D)
        if window_rate(r, lo, hi)[0] == 1.0:
            a = m
        else:
            b = m
    return round(a, 2)


CASES = {
    "default_historical": dict(mode="historical"),
    "default_bootstrap": dict(mode="bootstrap"),
    "default_normal": dict(mode="normal"),
    "default_normal_old_assumption": dict(mode="normal", stock=100, muS=5, sdS=13),
    "retire50_100pct_stocks_historical": dict(mode="historical", stock=100),
    "glide_90_to_50_historical": dict(mode="historical", stock=90, glide=True, stockAtRetire=50),
    "percent_rule_4pct_historical": dict(mode="historical", rule="percent", rate=4, floor=75),
    "guardrails_historical": dict(mode="historical", rule="guardrails"),
    "guardrails_bootstrap": dict(mode="bootstrap", rule="guardrails"),
    "pension_20k_at_67_historical": dict(mode="historical", pension=20_000, pensionAge=67),
    "pension_20k_at_67_bootstrap": dict(mode="bootstrap", pension=20_000, pensionAge=67),
    "block1_bootstrap": dict(mode="bootstrap", block=1),
    "block5_bootstrap": dict(mode="bootstrap", block=5),
    "block20_bootstrap": dict(mode="bootstrap", block=20),
    "trinity_50_historical": dict(RETIREE, stock=50),
    "trinity_75_historical": dict(RETIREE, stock=75),
    "trinity_75_bootstrap": dict(RETIREE, stock=75, mode="bootstrap"),
    "trinity_75_normal": dict(RETIREE, stock=75, mode="normal"),
}


def main():
    out = {"data": f"{D['first_year']}-{D['last_year']} (Shiller file ends {D['shiller_last_month']})"}
    bad = []

    bench = {}
    for stock, published in ((50, 0.95), (75, 0.98), (100, None)):
        r = engine.run(dict(RETIREE, stock=stock), D)
        t_rate, t_n, t_fail = window_rate(r, 1926, 1966)
        a_rate, a_n, a_fail = window_rate(r)
        bench[f"{stock}_stocks"] = dict(trinity_published=published, trinity_window=dict(rate=round(t_rate, 4), n=t_n, failed=t_fail),
                                        all_windows=dict(rate=round(a_rate, 4), n=a_n, failed=a_fail),
                                        safemax_1926_1966=safemax(stock, 1926, 1966), safemax_all=safemax(stock))
        if published is not None and abs(t_rate - published) > 0.06:
            bad.append(f"Trinity {stock}/{100 - stock}: {t_rate:.3f} vs published {published}")
    out["benchmark_4pct_30y"] = bench

    # Same benchmark on Damodaran's calendar-year real returns (Dec 31 closes), if the raw file is cached.
    dam = damodaran_series()
    if dam:
        db = {}
        for stock in (50, 75, 100):
            r = engine.run(dict(RETIREE, stock=stock), dam)
            t_rate, t_n, t_fail = window_rate(r, None, 1966)
            db[f"{stock}_stocks"] = dict(rate_1928_1966=round(t_rate, 4), n=t_n, failed=t_fail)
            print(f"Damodaran calendar years, 4% / 30y / {stock}% stocks, retirement years 1928-66: {t_rate:.1%} of {t_n}, failed {t_fail}")
        out["benchmark_damodaran_data"] = db
    fa = engine.run(dict(RETIREE, stock=75), D)
    out["fail_ages_75_stocks"] = {w["year"]: w["failAge"] for w in fa["windows"] if w["complete"] and w["failAge"]}
    out["benchmark_note"] = ("Trinity (1998) used S&P 500 and long-term high-grade corporate bonds, 1926-1995; Bengen (1994) "
                             "used S&P 500 and intermediate Treasuries and found 4.15% the worst-case rate at 50-75% stocks. "
                             "Here: Shiller S&P Composite and 10-year Treasuries, January to January.")

    # Holdout: fit the random modes on 1871-1945 only, then compare their predicted success with what
    # actually happened to 30-year retirements starting 1946-1993 (data the fit never saw).
    cut = D["year"].index(1946)
    train = dict(year=D["year"][:cut], stock=D["stock"][:cut], bond=D["bond"][:cut])
    hold = []
    for wr in (3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0):
        c = dict(RETIREE, stock=75, spend=wr * 10_000)
        realized, n, _ = window_rate(engine.run(c, D), 1946, None)
        row = dict(rate=wr, realized=round(realized, 4), n=n)
        for mode in ("bootstrap", "normal"):
            row[mode] = round(engine.run(dict(c, mode=mode, sims=4000), train)["rate"], 4)
        hold.append(row)
        print(f"holdout {wr:.1f}%: realized {realized:.1%} of {n} (1946-93 starts) | bootstrap fit 1871-1945 {row['bootstrap']:.1%} | normal {row['normal']:.1%}")
    out["holdout_1946_1993"] = dict(note="75/25, 30 years, constant real withdrawals; random modes fitted on 1871-1945 only; "
                                         "realized = share of 1946-1993 retirement years that lasted 30 years. Windows overlap, "
                                         "so 48 windows are worth only a few independent observations.", rows=hold)

    py = {}
    for k, c in CASES.items():
        r = engine.run(c, D)
        row = dict(rate=round(r["rate"], 4), n=r["n"], medEnd=round(r["medEnd"]) if r.get("medEnd") is not None else None)
        if r["mode"] == "historical":
            row["failed"] = [w["year"] for w in r["windows"] if w["complete"] and w["failAge"]]
            row["incomplete"] = [w["year"] for w in r["windows"] if not w["complete"]][:1] + [r["windows"][-1]["year"]]
        py[k] = row
    out["cases"] = py

    for k, b in bench.items():
        print(f"4% / 30y / {k:11s} retirement years 1926-66: {b['trinity_window']['rate']:.1%} of {b['trinity_window']['n']} "
              f"(Trinity {b['trinity_published']}), failed {b['trinity_window']['failed']}; "
              f"all {b['all_windows']['n']}: {b['all_windows']['rate']:.1%}; SAFEMAX {b['safemax_1926_1966']}% (1926-66), {b['safemax_all']}% (all)")
    for k, v in py.items():
        print(f"{k:36s} {v['rate']:.1%}  n={v['n']}  median end ${v['medEnd']:,}" + (f"  failed {v['failed']}" if 'failed' in v else ""))

    if "--js" in sys.argv:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page()
            pg.set_content("<!DOCTYPE html><title>engine check</title>")
            pg.add_script_tag(path=str(REPO / "data" / "returns.js"))
            pg.add_script_tag(path=str(REPO / "engine.js"))
            js = pg.evaluate("""cases => {
                const o = {};
                for (const k in cases) { const r = FireEngine.run(cases[k], self.RETURNS, false); o[k] = {rate: r.rate, medEnd: r.medEnd}; }
                return o; }""", CASES)
            b.close()
        diffs = 0
        for k in CASES:
            pr = engine.run(CASES[k], D)
            same_rate = abs(js[k]["rate"] - pr["rate"]) < 1e-12
            same_end = abs(js[k]["medEnd"] - pr["medEnd"]) <= 1e-6 * max(1.0, abs(pr["medEnd"]))
            if not (same_rate and same_end):
                diffs += 1
                bad.append(f"JS and Python differ on {k}: {js[k]} vs rate {pr['rate']} medEnd {pr['medEnd']}")
        out["js_matches_python"] = diffs == 0
        print(f"engine.js vs scripts/engine.py: {len(CASES) - diffs} of {len(CASES)} cases identical")

    (REPO / "data" / "validation.json").write_text(json.dumps(out, indent=1) + "\n")
    if bad:
        print("FAIL\n  " + "\n  ".join(bad))
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()
