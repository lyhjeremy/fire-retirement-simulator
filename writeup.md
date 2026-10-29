# When can I retire? Notes on the simulator

The page version with live charts is at [lyhjeremy.github.io/fire-retirement-simulator/overview/](https://lyhjeremy.github.io/fire-retirement-simulator/overview/).

## The original app (July 2026)

The first version was one HTML file. It played a plan forward a year at a time, 5,000 times, drawing each year's real return from a normal distribution with a mean and volatility the user set (defaults 5.0% and 13.0%), and reported the share of paths that never ran out. A search tried each retirement age in turn and stopped at the first that reached 90%. For the default plan (age 32, $150k invested, $40k a year saved, $60k a year spent, plan until 95) it reported 3% at 40, 56% at 50 and 90% first at 59.

Its README already named the weak points: independent normal draws have thin tails and no clustering of bad years, and the model had no bonds, glide path, pension or flexible spending.

## October 2026 upgrade

Dated 2026-10-28. The aim was a simulator built on real market history and on the choices people actually make.

### What changed

- **Data.** `scripts/build_returns.py` turns Robert Shiller's monthly `ie_data.xls` into annual real returns for the S&P Composite (dividends reinvested) and 10-year Treasuries, plus CPI inflation, January to January, 1871 to 2022. Bond returns use a constant-maturity approximation from the yield: buy a 10-year par bond, collect the coupon, sell it as a 9-year bond a year later. Shiller's file ends in September 2023, so 2022 is the last full year.
- **Three engines.** Normal draws (now a stock/bond pair with the data's means, spreads and correlation), a moving-block bootstrap of real years (default 10-year blocks), and historical replay of every retirement year.
- **Plan inputs.** Stock/bond mix with optional glide path to retirement, three spending rules (constant, percentage of portfolio, Guyton-Klinger-style guardrails with floor and ceiling), and a pension or Social Security amount from a chosen age.
- **Solver.** For the plan on screen, the smallest single change on each lever (retire later, spend less, save more, change the mix) that reaches a target, or the slack on each lever if the plan already clears it. It runs in a Web Worker.
- **Checks.** A Python port of the engine, a benchmark against the Trinity study and Bengen, a holdout test of the random engines, and a script that runs engine.js in headless Chromium and requires it to match the port.

### Why the headline moved

The default plan now uses 75% stocks and 25% bonds. Under the three engines it lasts in 82.2% of normal paths, 84.8% of bootstrap paths and 84 of 90 historical retirement years (93.3%). The old 56% came mostly from the 5.0% return assumption. US stocks returned 6.9% a year after inflation over 1871 to 2022, compounded, and the old assumption for the whole portfolio sat well under a 75/25 mix of that history. With the old assumption and a fixed seed, the engine gives 54.3%.

With the mean and spread held at history's values, changing only how years are drawn still moves the answer by 11 points. One-year bootstrap blocks give 82.6%, close to the normal engine, so fat tails alone do little to this plan. Longer blocks raise it (84.3% at 5 years, 84.8% at 10, 86.4% at 20) and replay raises it most. Over a 63-year plan, US history has tended to follow bad decades with better ones, and independent draws drop that. The replay number rests on 90 overlapping windows, roughly two independent lifetimes, so it is not precise.

### Which years fail

Historical replay aligns the whole life with history: retiring in 1929 means saving from 1911 to 1928. For this plan the failures are 1917 (out at 92) and 1973 to 1977 (out between 83 and 95). The 1929 and 1966 retirees, the textbook failures for a 30-year retiree with a fixed pot, both survive, because their working years built balances of $2.58 million and $2.77 million. The 1973 to 1977 retirees reach retirement with $0.85 to $1.5 million after weaker saving years, then face 6.6% to 8.7% a year inflation in their first decade.

### Benchmark

The 4% rule over 30 years, constant real withdrawals, historical windows starting 1926 to 1966: 92.7% at 50/50 and 95.1% at 75/25 on this data. The Trinity study (Cooley, Hubbard and Walz, 1998) reported 95% and 98%. Here 1964 to 1966 fail at 50/50 and 1965 and 1966 at 75/25, each running out in its 25th to 29th year. The highest rate that survives every window is 3.63% at 50/50 and 3.75% at 75/25, against Bengen's 4.15% (1994). Damodaran's calendar-year data gives the same failing years, which rules out January-to-January timing. The two studies used different bonds (Trinity long-term corporates, Bengen intermediate Treasuries); I did not test whether that accounts for the gap.

### Holdout

The random engines were fitted on 1871 to 1945 only and asked about a 30-year 75/25 retirement at withdrawal rates from 3% to 6%. Their answers were compared with the 48 retirements that actually started from 1946 to 1993:

| Rate | Actual | Bootstrap | Normal |
|---|---|---|---|
| 3.0% | 100.0% | 99.6% | 98.1% |
| 4.0% | 91.7% | 96.4% | 92.6% |
| 5.0% | 72.9% | 87.8% | 81.1% |
| 6.0% | 62.5% | 72.6% | 66.1% |

From 4% up, both engines overstated post-war success, and the bootstrap by more. The windows overlap heavily (1966 to 1969 share 27 of their 30 years), so the direction is clearer than the size.

### Spending rules

On the default plan, guardrails (floor 75%, ceiling 150% of $60k) lift bootstrap success from 84.8% to 90.0%; about a quarter of paths spend at least a year at the $45,000 floor. The percentage rule at 4% reaches 93.1% under the bootstrap, and its median path falls to $53,535 in its lowest year. A $20,000 pension from 67 under constant spending gives 89.9% under the bootstrap and 100% in history.

### Decisions

- Historical windows are aligned on the retirement year, with the working years taken from the years before it, so the start-year grid reads as "the year you retired".
- Retirement years after 1978 cannot finish a 45-year drawdown by 2022. They are drawn with their 2022 balance and left out of the success rate.
- The bootstrap wraps from 2022 back to 1871 so the end years are not underweighted.
- Guardrails compare total spending with the portfolio, so a pension starting later does not trigger raises.
- Results use a fixed seed (2026), so a plan always gives the same number and the solver compares plans on the same markets.
- 2023 is left out rather than spliced from another source, because Shiller's 2023 CPI is partly estimated.

### Limitations

One country's history, and a favorable one. No taxes, fees, one-off costs or spending that changes with age. One bond series. Few complete windows for long plans. It is an educational tool and does not give financial advice.
