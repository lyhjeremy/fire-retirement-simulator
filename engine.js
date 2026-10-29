/* FIRE simulator engine. Plain script, no dependencies: loads in the page, in a Web Worker
   (importScripts) and in the headless check (scripts/check_engine.py). Everything is in real
   (inflation-adjusted) dollars and real returns. scripts/engine.py is a line-for-line port. */
(function (root) {
  "use strict";

  /* Seeded uniform generator (mulberry32), so a plan always sees the same random markets. */
  function rng(seed) {
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) >>> 0;
      var t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function normal(r) {
    var u = 0, v = 0;
    while (u === 0) u = r();
    while (v === 0) v = r();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }

  var DEFAULTS = {
    age: 32, retire: 50, until: 95, balance: 150000, contrib: 40000, spend: 60000,
    mode: "historical",            /* "normal" | "bootstrap" | "historical" */
    sims: 5000, seed: 2026, block: 10,
    stock: 75,                     /* % stocks now (or throughout, without a glide path) */
    glide: false, stockAtRetire: 50, /* glide path: straight line from stock to stockAtRetire, then held */
    rule: "constant",              /* "constant" | "percent" | "guardrails" */
    rate: 4,                       /* % of portfolio, percent rule */
    floor: 75, ceiling: 150,       /* % of target spending, percent and guardrails rules */
    pension: 0, pensionAge: 67,    /* real $ a year from pensionAge */
    muS: null, sdS: null           /* normal mode stock mean and sd (%); null = the data's */
  };

  function fill(p) {
    var o = {}, k;
    for (k in DEFAULTS) o[k] = DEFAULTS[k];
    for (k in p) if (p[k] !== undefined && p[k] !== null) o[k] = p[k];
    return o;
  }

  function stats(xs) {
    var n = xs.length, m = 0, i;
    for (i = 0; i < n; i++) m += xs[i];
    m /= n;
    var v = 0;
    for (i = 0; i < n; i++) v += (xs[i] - m) * (xs[i] - m);
    return { mean: m, sd: Math.sqrt(v / (n - 1)) };
  }
  function corr(a, b) {
    var sa = stats(a), sb = stats(b), c = 0;
    for (var i = 0; i < a.length; i++) c += (a[i] - sa.mean) * (b[i] - sb.mean);
    return c / (a.length - 1) / (sa.sd * sb.sd);
  }

  /* Stock share in plan year y (1-based). Working years are 1..W. */
  function shareAt(p, y, W) {
    if (!p.glide) return p.stock / 100;
    if (y > W || W <= 1) return p.stockAtRetire / 100;
    return (p.stock + (p.stockAtRetire - p.stock) * (y - 1) / (W - 1)) / 100;
  }

  /* Play one path. rs, rb: real stock and bond returns for plan years 1..T (index y-1).
     Returns balances by year (0..T) in bal[], plus outcome fields. Working years add the
     contribution at year end; retirement years withdraw at the start of the year. */
  function playPath(p, rs, rb, T, W, bal) {
    var b = p.balance, failAge = 0, spend = p.spend, C = spend, iwr = 0, minC = Infinity, sumC = 0, nC = 0, floorHit = false;
    var lo = p.floor / 100 * spend, hi = p.ceiling / 100 * spend;
    bal[0] = b;
    for (var y = 1; y <= T; y++) {
      var age = p.age + y, w = shareAt(p, y, W), r = w * rs[y - 1] + (1 - w) * rb[y - 1];
      if (y <= W) {
        b = b * (1 + r) + p.contrib;
      } else {
        var pen = age >= p.pensionAge ? p.pension : 0;
        if (failAge) { bal[y] = 0; continue; }
        if (p.rule === "percent") {
          C = p.rate / 100 * b + pen;
          if (C < lo) C = lo;
          if (C > hi) C = hi;
        } else if (p.rule === "guardrails") {
          if (y === W + 1) { C = spend; iwr = b > 0 ? spend / b : Infinity; }
          else {
            var wr = b > 0 ? C / b : Infinity, left = T - y + 1;
            if (wr > iwr * 1.2 && left > 15) C *= 0.9;          /* capital preservation rule */
            else if (wr < iwr * 0.8) C *= 1.1;                    /* prosperity rule */
            if (C < lo) C = lo;
            if (C > hi) C = hi;
          }
        } else {
          C = spend;
        }
        if (C < minC) minC = C;
        if (C <= lo + 1e-6 && p.rule !== "constant") floorHit = true;
        sumC += C; nC++;
        var wd = C - pen;
        if (wd < 0) wd = 0;
        if (wd > b) { b = 0; failAge = age; bal[y] = 0; continue; }
        b = (b - wd) * (1 + r);
      }
      bal[y] = b;
    }
    return { failAge: failAge, end: b, minC: nC ? minC : spend, avgC: nC ? sumC / nC : spend, floorHit: floorHit };
  }

  function quant(sorted, f) {
    return sorted[Math.min(sorted.length - 1, Math.floor(f * (sorted.length - 1)))];
  }

  /* Historical replay: one window per retirement year. Working years use the years just
     before it, so "retired in 1929" means the whole life lines up with 1929 as the first
     year of retirement. Windows that run past the data's last year are kept as incomplete. */
  function historical(p, D, keep) {
    var T = p.until - p.age, W = Math.max(0, Math.min(T, p.retire - p.age));
    var first = D.year[0], last = D.year[D.year.length - 1];
    var bal = new Float64Array(T + 1), wins = [], cols = [], ok = 0, n = 0;
    var rs = new Float64Array(T), rb = new Float64Array(T);
    for (var Ry = first + W; Ry <= last; Ry++) {
      var start = Ry - W - first, avail = Math.min(T, D.year.length - start), complete = avail === T;
      for (var y = 0; y < T; y++) {
        rs[y] = y < avail ? D.stock[start + y] : 0;
        rb[y] = y < avail ? D.bond[start + y] : 0;
      }
      var res = playPath(p, rs, rb, avail, W, bal);
      var win = { year: Ry, complete: complete, failAge: res.failAge, end: res.end, minC: res.minC, avgC: res.avgC,
                  atRet: bal[Math.min(W, avail)], through: Ry - W + avail - 1 };
      if (keep) win.path = Array.prototype.slice.call(bal, 0, avail + 1);
      wins.push(win);
      if (complete) {
        n++;
        if (!res.failAge) ok++;
        if (keep) cols.push(Array.prototype.slice.call(bal, 0, T + 1));
      }
    }
    var out = { mode: "historical", rate: n ? ok / n : NaN, n: n, years: T, W: W, windows: wins };
    summarize(out, wins.filter(function (w) { return w.complete; }), cols, T, keep);
    return out;
  }

  function summarize(out, rows, cols, T, keep) {
    if (!rows.length) return;
    var sortBy = function (f) { return rows.map(f).sort(function (a, b) { return a - b; }); };
    out.medRet = quant(sortBy(function (w) { return w.atRet; }), 0.5);
    out.medEnd = quant(sortBy(function (w) { return w.end; }), 0.5);
    out.medMinC = quant(sortBy(function (w) { return w.minC; }), 0.5);
    out.p10MinC = quant(sortBy(function (w) { return w.minC; }), 0.1);
    out.medAvgC = quant(sortBy(function (w) { return w.avgC; }), 0.5);
    if (keep && cols.length) {
      ["p10", "p25", "p50", "p75", "p90"].forEach(function (k) {
        var f = +k.slice(1) / 100, arr = new Array(T + 1), tmp = new Float64Array(cols.length);
        for (var y = 0; y <= T; y++) {
          for (var s = 0; s < cols.length; s++) tmp[s] = cols[s][y];
          tmp.sort();
          arr[y] = quant(tmp, f);
        }
        out[k] = arr;
      });
    }
  }

  /* Normal and bootstrap modes: many random paths. */
  function montecarlo(p, D, keep) {
    var T = p.until - p.age, W = Math.max(0, Math.min(T, p.retire - p.age)), N = p.sims, r = rng(p.seed);
    var bal = new Float64Array(T + 1), rs = new Float64Array(T), rb = new Float64Array(T);
    var cols = keep ? [] : null, rows = [], ok = 0, L = D.year.length;
    var ss = stats(D.stock), sb = stats(D.bond), rho = corr(D.stock, D.bond);
    var muS = p.muS === null ? ss.mean : p.muS / 100, sdS = p.sdS === null ? ss.sd : p.sdS / 100;
    var muB = sb.mean, sdB = sb.sd, k2 = Math.sqrt(1 - rho * rho), blk = Math.max(1, Math.round(p.block));
    for (var s = 0; s < N; s++) {
      if (p.mode === "normal") {
        for (var y = 0; y < T; y++) {
          var z1 = normal(r), z2 = normal(r);
          rs[y] = Math.max(-0.99, muS + sdS * z1);
          rb[y] = Math.max(-0.99, muB + sdB * (rho * z1 + k2 * z2));
        }
      } else {
        /* moving-block bootstrap with wraparound: random start year, then blk years in order */
        for (var y2 = 0; y2 < T; ) {
          var st = Math.floor(r() * L);
          for (var j = 0; j < blk && y2 < T; j++, y2++) {
            var ix = (st + j) % L;
            rs[y2] = D.stock[ix]; rb[y2] = D.bond[ix];
          }
        }
      }
      var res = playPath(p, rs, rb, T, W, bal);
      if (!res.failAge) ok++;
      rows.push({ atRet: bal[W], end: res.end, minC: res.minC, avgC: res.avgC, failAge: res.failAge, floorHit: res.floorHit });
      if (keep) cols.push(Float64Array.from(bal));
    }
    var out = { mode: p.mode, rate: ok / N, n: N, years: T, W: W };
    summarize(out, rows, cols || [], T, keep);
    if (keep) {
      var fails = rows.filter(function (w) { return w.failAge; }).map(function (w) { return w.failAge; }).sort(function (a, b) { return a - b; });
      out.medFailAge = fails.length ? quant(fails, 0.5) : null;
      out.floorShare = rows.filter(function (w) { return w.floorHit; }).length / N;
    }
    return out;
  }

  function run(params, D, keep) {
    var p = fill(params);
    if (p.mode === "historical") return historical(p, D, keep);
    return montecarlo(p, D, keep);
  }

  /* Smallest single change on each lever that reaches the target success rate. When the plan
     already reaches it, each lever reports how far it could move the other way and still hold
     (retire earlier, spend more, save less). Normal and bootstrap runs reuse one seed, so
     every candidate faces the same markets. */
  function solve(params, D, target, sims) {
    var p = fill(params);
    if (p.mode !== "historical") p.sims = sims || 2000;
    var rate = function (ch) { var q = fill(p); for (var k in ch) q[k] = ch[k]; return run(q, D, false).rate; };
    var base = rate({}), met = base >= target, out = { target: target, base: base, met: met, levers: {} };
    var ok = function (ch) { return rate(ch) >= target; };

    /* largest x in [lo, hi] with good(x), assuming good is true at lo and falls as x rises */
    function bisect(lo, hi, good, step) {
      for (var i = 0; i < 24 && hi - lo > step / 2; i++) {
        var mid = (lo + hi) / 2;
        if (good(mid)) lo = mid; else hi = mid;
      }
      return lo;
    }

    /* retirement age */
    var ra = null;
    if (!met) {
      for (var a = p.retire + 1; a <= p.until - 1; a++) if (ok({ retire: a })) { ra = a; break; }
    } else {
      ra = p.retire;
      for (var a2 = p.retire - 1; a2 >= p.age; a2--) { if (ok({ retire: a2 })) ra = a2; else break; }
    }
    out.levers.retire = { value: ra, from: p.retire };

    /* spending, to $500 */
    var sv = null;
    if (!met) {
      if (ok({ spend: 0 })) {
        sv = Math.floor(bisect(0, p.spend, function (x) { return ok({ spend: x }); }, 250) / 500) * 500;
        while (sv > 0 && !ok({ spend: sv })) sv -= 500;
      }
    } else {
      var hiS = p.spend * 2;
      while (hiS < p.spend * 64 && ok({ spend: hiS })) hiS *= 2;
      sv = Math.floor(bisect(p.spend, hiS, function (x) { return ok({ spend: x }); }, 250) / 500) * 500;
      if (sv < p.spend) sv = p.spend;
    }
    out.levers.spend = { value: sv, from: p.spend };

    /* yearly contribution, to $500 */
    var cv = null, na = p.retire <= p.age;
    if (!na) {
      if (!met) {
        var cap = Math.max(2000000, p.contrib * 20), hiC = Math.max(p.contrib * 2, 20000);
        while (hiC < cap && !ok({ contrib: hiC })) hiC *= 2;
        if (ok({ contrib: hiC })) {
          /* smallest passing contribution: bisect on the negated value */
          var neg = bisect(-hiC, -p.contrib, function (x) { return ok({ contrib: -x }); }, 250);
          cv = Math.ceil(-neg / 500) * 500;
        }
      } else {
        if (ok({ contrib: 0 })) cv = 0;
        else cv = Math.ceil(-bisect(-p.contrib, 0, function (x) { return ok({ contrib: -x }); }, 250) / 500) * 500;
      }
    }
    out.levers.contrib = { value: cv, from: p.contrib, na: na };

    /* allocation: fixed stock share nearest the current one that reaches the target */
    var curve = [], best = null, cur = p.glide ? p.stockAtRetire : p.stock;
    for (var sh = 0; sh <= 100; sh += 5) {
      var rr = rate({ stock: sh, glide: false });
      curve.push([sh, rr]);
      if (rr >= target && (best === null || Math.abs(sh - cur) < Math.abs(best - cur))) best = sh;
    }
    var passing = curve.filter(function (c) { return c[1] >= target; }).map(function (c) { return c[0]; });
    out.levers.stock = { value: best, from: cur, glide: p.glide, curve: curve,
                         range: passing.length ? [passing[0], passing[passing.length - 1]] : null };
    return out;
  }


  var api = { rng: rng, normal: normal, run: run, solve: solve, DEFAULTS: DEFAULTS, fill: fill, stats: stats, corr: corr };
  root.FireEngine = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof self !== "undefined" ? self : this);
