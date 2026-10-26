# When can I retire? A FIRE Monte Carlo simulator

A browser-based retirement simulator that runs 5,000 randomized market paths and reports the probability your savings last, plus the earliest retirement age that reaches 90%.

[Live app](https://lyhjeremy.github.io/fire-retirement-simulator/) · [Write-up](https://lyhjeremy.github.io/fire-retirement-simulator/overview/)

Design and copy follow [these standards](https://github.com/lyhjeremy/lyhjeremy/blob/main/DESIGN_STANDARDS.md).

![Result card reading 56% chance of never running out by age 95, above a fan chart whose percentile bands widen after retirement at 50](overview/result-card.png)

## Results

The app's default plan (age 32, $150k saved, $40k a year contributed, $60k a year spent, 5.0% real return, 13.0% volatility, plan until 95), run with only the retirement age changed:

| Retire at | Success rate | Median at retirement | Median at 95 |
|---|---|---|---|
| 40 | 3% | $582,492 | $0 |
| 50 | 56% | $1,373,084 | $742,816 |
| 59 | 90% | $2,414,598 | $5,558,280 |

59 is the age the built-in "Find earliest age for 90% success" search returned. At 50 the withdrawal rate is about 4.4% of the median portfolio, close to the 4% rule, yet 44% of paths run out before 95. Each run uses fresh random draws, so reruns move these figures slightly.

## Method

- Monte Carlo simulation, 5,000 paths per run. Each path steps forward one year at a time from current age to the plan-until age.
- Each year's real return is drawn from a normal distribution (Box-Muller transform) with the user's mean and volatility. Contributions are added while working; spending is subtracted after retirement. A path that goes below zero is marked as failed.
- Success rate is the share of paths that never hit zero. The fan chart shows the 10th, 25th, 50th, 75th and 90th percentile balance at every age.
- The earliest-age search tries each retirement age in turn at 2,500 paths and stops at the first that reaches 90%, then reruns that age at 5,000 paths.

## Stack

One HTML file with vanilla JavaScript and a `<canvas>` chart. No dependencies, no build step, no backend, no analytics. Nothing you type leaves the browser.

## How to run

Open `index.html` in a browser, or use the [live app](https://lyhjeremy.github.io/fire-retirement-simulator/).

## Limitations

- Returns are independent normal draws. Real returns have fatter tails and bad years that cluster, so the model is probably somewhat optimistic about the worst cases.
- Return and spending are constant in real terms. No taxes, pensions, stock/bond glide path, one-off costs, or spending cuts in bad years.
- It is an educational tool for comparing plans, not financial advice.

## License

[MIT](LICENSE) © 2026 Jeremy Lee
