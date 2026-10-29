"""Build data/returns.json: annual real returns for US stocks and 10-year Treasuries, 1871 on.

Source: Robert Shiller's monthly data, http://www.econ.yale.edu/~shiller/data/ie_data.xls
Cross-check: Aswath Damodaran's histretSP.xls (NYU Stern), sheet "Nominal vs Real Data".

Usage:
    python3 scripts/build_returns.py            # reads ~/data-cache/fire-retirement-simulator/
    python3 scripts/build_returns.py --download # fetches both files first

Needs xlrd (reads the old .xls format). Writes data/returns.json, data/returns.js (the same data for the browser) and data/crosscheck.json.

Method, all on January values so each "year" runs January to January:
  stocks    chain the monthly total return (P[m+1] + D[m]/12) / P[m] from January of
            year Y to January of Y+1. P is the S&P Composite monthly average price and D
            the annualized dividend, as in Shiller's own total-return column.
  bonds     a constant-maturity approximation from the GS10 yield column (long-term
            government yields before 1953). Buy a 10-year par bond at January's yield y0,
            collect the coupon y0, and sell it a year later as a 9-year bond priced at the
            next January's yield y1:
                R = y0 + y0 * (1 - (1 + y1)^-9) / y1 + (1 + y1)^-9 - 1
            Annual coupons, no taxes or costs.
  inflation CPI January Y+1 / CPI January Y - 1.
  real      (1 + nominal) / (1 + inflation) - 1.
"""
import json, os, sys, urllib.request
from pathlib import Path

import xlrd

CACHE = Path.home() / "data-cache" / "fire-retirement-simulator"
REPO = Path(__file__).resolve().parent.parent
SHILLER_URL = "http://www.econ.yale.edu/~shiller/data/ie_data.xls"
DAMODARAN_URL = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/histretSP.xls"


def download():
    CACHE.mkdir(parents=True, exist_ok=True)
    for url in (SHILLER_URL, DAMODARAN_URL):
        dest = CACHE / url.rsplit("/", 1)[1]
        print("fetching", url)
        urllib.request.urlretrieve(url, dest)


def read_shiller():
    sh = xlrd.open_workbook(CACHE / "ie_data.xls").sheet_by_name("Data")
    rows = {}
    for r in range(8, sh.nrows):
        d = sh.cell_value(r, 0)
        if not isinstance(d, float):
            continue
        year = int(d)
        month = int(round((d - year) * 100))
        p, div, cpi, gs10 = (sh.cell_value(r, c) for c in (1, 2, 4, 6))
        bond_ret = sh.cell_value(r, 17)
        rows[(year, month)] = dict(p=p, d=div if isinstance(div, float) else None, cpi=cpi,
                                   gs10=gs10, shiller_bond=bond_ret if isinstance(bond_ret, float) else None)
    last = max(rows)
    return rows, last


def bond_return(y0, y1, n=9):
    disc = (1 + y1) ** -n
    return y0 + y0 * (1 - disc) / y1 + disc - 1


def build(rows):
    years = sorted({y for (y, m) in rows})
    out = []
    for Y in years:
        if (Y + 1, 1) not in rows:
            break
        # stocks need dividends for all 12 months of the year
        growth, ok = 1.0, True
        for m in range(1, 13):
            a = rows.get((Y, m))
            b = rows.get((Y + 1, 1)) if m == 12 else rows.get((Y, m + 1))
            if a is None or b is None or a["d"] is None:
                ok = False
                break
            growth *= (b["p"] + a["d"] / 12) / a["p"]
        if not ok:
            break
        j0, j1 = rows[(Y, 1)], rows[(Y + 1, 1)]
        infl = j1["cpi"] / j0["cpi"] - 1
        bnom = bond_return(j0["gs10"] / 100, j1["gs10"] / 100)
        # Shiller's own monthly bond return, chained, for comparison only
        sb = 1.0
        for m in range(1, 13):
            v = rows[(Y, m)]["shiller_bond"]
            sb = sb * v if v is not None else float("nan")
        out.append(dict(year=Y, stock_nom=growth - 1, bond_nom=bnom, infl=infl,
                        stock=growth / (1 + infl) - 1, bond=(1 + bnom) / (1 + infl) - 1,
                        shiller_bond_nom=sb - 1))
    return out


def read_damodaran():
    sh = xlrd.open_workbook(CACHE / "histretSP.xls").sheet_by_name("Nominal vs Real Data")
    d = {}
    for r in range(1, sh.nrows):
        y = sh.cell_value(r, 0)
        if isinstance(y, float) and 1900 < y < 2100 and isinstance(sh.cell_value(r, 5), float):
            d[int(y)] = dict(stock_nom=sh.cell_value(r, 1), bond_nom=sh.cell_value(r, 3),
                             infl=sh.cell_value(r, 4), stock=sh.cell_value(r, 5), bond=sh.cell_value(r, 7))
    return d


def stats(xs):
    n = len(xs)
    m = sum(xs) / n
    sd = (sum((x - m) ** 2 for x in xs) / (n - 1)) ** 0.5
    g = 1.0
    for x in xs:
        g *= 1 + x
    return dict(mean=m, sd=sd, geo=g ** (1 / n) - 1, n=n)


def corr(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return cov / (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5


def main():
    if "--download" in sys.argv:
        download()
    rows, last = read_shiller()
    data = build(rows)
    first, final = data[0]["year"], data[-1]["year"]
    S = [r["stock"] for r in data]
    B = [r["bond"] for r in data]
    I = [r["infl"] for r in data]
    summary = dict(stock=stats(S), bond=stats(B), infl=stats(I), corr_stock_bond=corr(S, B))
    rnd = lambda x: round(x, 5)
    js = dict(
        source=("Robert Shiller, ie_data.xls (S&P Composite price and dividends, CPI, GS10), "
                "http://www.econ.yale.edu/~shiller/data/ie_data.xls; annual returns built by scripts/build_returns.py"),
        shiller_last_month=f"{last[0]}-{last[1]:02d}",
        first_year=first, last_year=final,
        definition=("Each year runs January to January. stock: S&P Composite total return, dividends reinvested monthly. "
                    "bond: 10-year Treasury (long-term government yield before 1953), constant-maturity approximation "
                    "from January yields, sold as a 9-year bond after one year. All returns real (deflated by CPI)."),
        summary={k: ({kk: rnd(vv) if isinstance(vv, float) else vv for kk, vv in v.items()} if isinstance(v, dict) else rnd(v))
                 for k, v in summary.items()},
        year=[r["year"] for r in data],
        stock=[rnd(x) for x in S], bond=[rnd(x) for x in B], infl=[rnd(x) for x in I],
    )
    (REPO / "data").mkdir(exist_ok=True)
    (REPO / "data" / "returns.json").write_text(json.dumps(js, separators=(",", ":")) + "\n")
    # Same data as a script, so the app also works from file:// and inside a Web Worker
    (REPO / "data" / "returns.js").write_text(
        "/* Generated by scripts/build_returns.py from data/returns.json. Do not edit. */\n"
        "self.RETURNS = " + json.dumps(js, separators=(",", ":")) + ";\n")
    print(f"returns.json: {first}-{final}, {len(data)} years; Shiller file ends {last[0]}-{last[1]:02d}")
    for k in ("stock", "bond", "infl"):
        s = summary[k]
        print(f"  {k:6s} mean {s['mean']:.4f} sd {s['sd']:.4f} geo {s['geo']:.4f}")
    print(f"  corr(stock, bond) {summary['corr_stock_bond']:.3f}")

    # Cross-check against Damodaran (calendar years, Dec-Dec; ours are Jan-Jan monthly averages)
    dm = read_damodaran()
    ours = {r["year"]: r for r in data}
    common = sorted(set(dm) & set(ours))
    check_years = [1931, 1937, 1966, 1974, 1987, 2000, 2008, 2022]
    table = []
    for y in check_years:
        if y in ours and y in dm:
            o, d = ours[y], dm[y]
            table.append(dict(year=y, ours_stock=rnd(o["stock"]), dam_stock=rnd(d["stock"]),
                              ours_bond=rnd(o["bond"]), dam_bond=rnd(d["bond"]),
                              ours_infl=rnd(o["infl"]), dam_infl=rnd(d["infl"])))
    agg = {}
    for k in ("stock", "bond", "infl"):
        a = [ours[y][k] for y in common]
        b = [dm[y][k] for y in common]
        agg[k] = dict(ours=stats(a), damodaran=stats(b), corr=corr(a, b),
                      mean_abs_diff=sum(abs(x - z) for x, z in zip(a, b)) / len(a))
    # Shiller's own bond series vs ours, same Jan-Jan window
    sb = [(r["shiller_bond_nom"], r["bond_nom"]) for r in data if r["shiller_bond_nom"] == r["shiller_bond_nom"]]
    agg["bond_vs_shiller_monthly"] = dict(n=len(sb), corr=corr([x for x, _ in sb], [y for _, y in sb]),
                                          mean_abs_diff=sum(abs(x - y) for x, y in sb) / len(sb))
    cc = dict(note=("Damodaran histretSP.xls 'Nominal vs Real Data', calendar years from Dec 31 closes; "
                    "ours run January to January on monthly averages, so single years differ by timing."),
              years=f"{common[0]}-{common[-1]}", sample=table,
              aggregate=json.loads(json.dumps(agg, default=float)))
    (REPO / "data" / "crosscheck.json").write_text(json.dumps(cc, indent=1) + "\n")
    print(f"crosscheck vs Damodaran {common[0]}-{common[-1]} ({len(common)} years)")
    for k in ("stock", "bond", "infl"):
        a = agg[k]
        print(f"  {k:6s} ours mean {a['ours']['mean']:.4f} sd {a['ours']['sd']:.4f} | dam mean {a['damodaran']['mean']:.4f} "
              f"sd {a['damodaran']['sd']:.4f} | corr {a['corr']:.3f} mad {a['mean_abs_diff']:.4f}")
    a = agg["bond_vs_shiller_monthly"]
    print(f"  bond vs Shiller monthly bond column: corr {a['corr']:.4f}, mean abs diff {a['mean_abs_diff']:.4f} over {a['n']} years")
    for t in table:
        print("  ", t)


if __name__ == "__main__":
    main()
