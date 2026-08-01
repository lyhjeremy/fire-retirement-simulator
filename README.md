# When Can I Retire? — a FIRE Monte-Carlo simulator

A free, browser-based retirement simulator. Instead of a single rule of thumb
("save 25× your spending"), it runs **thousands of randomized market scenarios**
and reports the *probability* your money lasts — plus the earliest age you could
retire at 90% confidence.

> 🌐 **Try it:** https://lyhjeremy.github.io/fire-retirement-simulator/
> 📖 **Product overview:** https://lyhjeremy.github.io/fire-retirement-simulator/overview/

## What it does
- Plays your plan forward year by year: contributions until retirement, then
  withdrawals, with each year's return drawn from a bell curve around the average
  real return and volatility you choose.
- Reports a **success rate** (share of scenarios in which you never run out before
  your plan-until age) and a **fan chart** of percentile outcomes over time.
- "**Find earliest age for 90% success**" searches retirement ages for you.

## Why Monte-Carlo
The 4% rule and "25× expenses" are averages. You retire once, and *sequence of
returns* matters: a crash early in retirement is far more damaging than the same
crash later. Simulating thousands of randomized futures turns a fragile yes/no
answer into an honest probability.

## Tech
Vanilla HTML/CSS/JavaScript, no dependencies, no backend — everything runs in your
browser and no data leaves your machine. The chart is drawn on a `<canvas>`;
returns use a Box–Muller normal draw.

This is an educational tool, **not financial advice**.

## License
[MIT](LICENSE) © 2026 Jeremy Lee
