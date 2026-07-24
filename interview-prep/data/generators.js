/* Math drill generators.
   Each generator emits infinite variants at two difficulties:
     clean   - resolves in your head in ~15s
     precise - messy figures, grind it out
   Tables are static per generator and appear only where a table genuinely teaches. */

const pick = (a) => a[Math.floor(Math.random() * a.length)];
const pct = (x, d = 1) => (x * 100).toFixed(d) + "%";
const mx = (x, d = 2) => x.toFixed(d) + "x";
const money = (x) => "$" + x.toFixed(0);

/* ---------- static teaching tables ---------- */

const T_DOUBLE = `<table><thead><tr><th>Growth</th><th>Rule of 72</th><th>Actual</th></tr></thead><tbody>
<tr><td>4%</td><td>18.0</td><td>17.7</td></tr>
<tr><td>6%</td><td>12.0</td><td>11.9</td></tr>
<tr><td>8%</td><td>9.0</td><td>9.0</td></tr>
<tr><td>10%</td><td>7.2</td><td>7.3</td></tr>
<tr><td>12%</td><td>6.0</td><td>6.1</td></tr>
<tr><td>15%</td><td>4.8</td><td>5.0</td></tr>
<tr><td>20%</td><td>3.6</td><td>3.8</td></tr>
<tr><td>25%</td><td>2.9</td><td>3.1</td></tr>
<tr><td>30%</td><td>2.4</td><td>2.6</td></tr>
<tr><td>40%</td><td>1.8</td><td>2.1</td></tr>
<tr><td>50%</td><td>1.4</td><td>1.7</td></tr></tbody></table>
<p class="tnote">Compounding grid &mdash; what $1 becomes:</p>
<table><thead><tr><th>Growth</th><th>1y</th><th>2y</th><th>3y</th><th>4y</th><th>5y</th><th>10y</th></tr></thead><tbody>
<tr><td>5%</td><td>1.05</td><td>1.10</td><td>1.16</td><td>1.22</td><td>1.28</td><td>1.63</td></tr>
<tr><td>10%</td><td>1.10</td><td>1.21</td><td>1.33</td><td>1.46</td><td>1.61</td><td>2.59</td></tr>
<tr><td>15%</td><td>1.15</td><td>1.32</td><td>1.52</td><td>1.75</td><td>2.01</td><td>4.05</td></tr>
<tr><td>20%</td><td>1.20</td><td>1.44</td><td>1.73</td><td>2.07</td><td>2.49</td><td>6.19</td></tr>
<tr><td>25%</td><td>1.25</td><td>1.56</td><td>1.95</td><td>2.44</td><td>3.05</td><td>9.31</td></tr>
<tr><td>30%</td><td>1.30</td><td>1.69</td><td>2.20</td><td>2.86</td><td>3.71</td><td>13.79</td></tr></tbody></table>`;

const T_IRR = `<table><thead><tr><th>MoM</th><th>1y</th><th>2y</th><th>3y</th><th>4y</th><th>5y</th><th>7y</th><th>10y</th></tr></thead><tbody>
<tr><td>1.25x</td><td>25%</td><td>12%</td><td>8%</td><td>6%</td><td>5%</td><td>&mdash;</td><td>&mdash;</td></tr>
<tr><td>1.3x</td><td>30%</td><td>14%</td><td>9%</td><td>7%</td><td>5%</td><td>&mdash;</td><td>&mdash;</td></tr>
<tr><td>1.5x</td><td>50%</td><td>22%</td><td>14%</td><td>11%</td><td>8%</td><td>6%</td><td>4%</td></tr>
<tr><td>2x</td><td>100%</td><td>41%</td><td>26%</td><td>19%</td><td>15%</td><td>10%</td><td>7%</td></tr>
<tr><td>2.5x</td><td>150%</td><td>58%</td><td>36%</td><td>26%</td><td>20%</td><td>14%</td><td>10%</td></tr>
<tr><td>3x</td><td>200%</td><td>73%</td><td>44%</td><td>32%</td><td>25%</td><td>17%</td><td>12%</td></tr>
<tr><td>4x</td><td>300%</td><td>100%</td><td>59%</td><td>41%</td><td>32%</td><td>22%</td><td>15%</td></tr>
<tr><td>5x</td><td>400%</td><td>124%</td><td>71%</td><td>49%</td><td>38%</td><td>26%</td><td>17%</td></tr>
<tr><td>10x</td><td>900%</td><td>216%</td><td>115%</td><td>78%</td><td>59%</td><td>39%</td><td>26%</td></tr></tbody></table>`;

const T_DRAG = `<table><thead><tr><th>Multiple change</th><th>2y</th><th>3y</th><th>5y</th></tr></thead><tbody>
<tr><td>&minus;10%</td><td>&minus;5.1%</td><td>&minus;3.4%</td><td>&minus;2.1%</td></tr>
<tr><td>&minus;20%</td><td>&minus;10.6%</td><td>&minus;7.2%</td><td>&minus;4.4%</td></tr>
<tr><td>&minus;30%</td><td>&minus;16.3%</td><td>&minus;11.2%</td><td>&minus;6.9%</td></tr>
<tr><td>&minus;40%</td><td>&minus;22.5%</td><td>&minus;15.7%</td><td>&minus;9.7%</td></tr>
<tr><td>&minus;50%</td><td>&minus;29.3%</td><td>&minus;20.6%</td><td>&minus;12.9%</td></tr></tbody></table>`;

const T_YIELD = `<table><thead><tr><th>Multiple</th><th>Yield</th><th>Multiple</th><th>Yield</th></tr></thead><tbody>
<tr><td>8x</td><td>12.5%</td><td>25x</td><td>4.0%</td></tr>
<tr><td>10x</td><td>10.0%</td><td>30x</td><td>3.3%</td></tr>
<tr><td>12.5x</td><td>8.0%</td><td>35x</td><td>2.9%</td></tr>
<tr><td>15x</td><td>6.7%</td><td>40x</td><td>2.5%</td></tr>
<tr><td>20x</td><td>5.0%</td><td>50x</td><td>2.0%</td></tr></tbody></table>`;

/* ---------- generators ---------- */

const MATH_GENERATORS = [
  {
    id: "double",
    name: "Time to double",
    bucket: "Return math",
    table: T_DOUBLE,
    teaching:
      "Rule of 72 is excellent from 6&ndash;12% and drifts at the extremes. Above ~20% it <em>understates</em> how long doubling takes &mdash; always round up. Memorise the anchors outright: 10% &rarr; 7 years, 15% &rarr; 5 years, 20% &rarr; 3.8 years, 30% &rarr; 2.6 years.",
    gen(mode) {
      const r =
        mode === "clean"
          ? pick([6, 8, 9, 10, 12, 15, 18, 20, 25, 30]) / 100
          : pick([7.4, 11.3, 13.8, 16.2, 19.6, 23.5, 27.1]) / 100;
      const actual = Math.log(2) / Math.log(1 + r);
      const r72 = 72 / (r * 100);
      return {
        q: `Earnings compound at ${pct(r, mode === "clean" ? 0 : 1)} a year. How long until they double?`,
        a: `${actual.toFixed(1)} years`,
        method: [
          `Rule of 72: 72 &divide; ${(r * 100).toFixed(mode === "clean" ? 0 : 1)} = <strong>${r72.toFixed(1)} years</strong>`,
          `Exact: ln2 &divide; ln(1+r) = <strong>${actual.toFixed(1)} years</strong>`,
          r * 100 >= 20
            ? `At this rate the rule is optimistic by ${(actual - r72).toFixed(1)} years &mdash; round up.`
            : `The rule is accurate to within ${Math.abs(actual - r72).toFixed(1)} years here.`,
        ],
      };
    },
  },

  {
    id: "mom_irr",
    name: "MoM &harr; IRR",
    bucket: "Return math",
    table: T_IRR,
    teaching:
      "For a 12-month-horizon fund you live in the top-left of this table. A 1.3x in a year is a great outcome; a 1.3x that takes three years is a 9% compounder you should not own concentrated. Time is the variable people forget to argue about &mdash; most thesis disagreements are timing disagreements wearing a valuation costume.",
    gen(mode) {
      const reverse = Math.random() < 0.4;
      const n = pick([2, 3, 4, 5]);
      if (reverse) {
        const hurdle = mode === "clean" ? pick([15, 20, 25, 30]) / 100 : pick([17.5, 22.5, 27.5]) / 100;
        const need = Math.pow(1 + hurdle, n);
        return {
          q: `You need a ${pct(hurdle, mode === "clean" ? 0 : 1)} IRR over ${n} years. What multiple of money does that require?`,
          a: mx(need),
          method: [
            `MoM = (1 + IRR)<sup>n</sup> = (1 + ${hurdle.toFixed(3)})<sup>${n}</sup>`,
            `= <strong>${mx(need)}</strong> over ${n} years`,
            `Sense-check against the grid: ${n}y at roughly this hurdle sits near the ${need < 1.5 ? "1.25&ndash;1.5x" : need < 2 ? "1.5&ndash;2x" : need < 3 ? "2&ndash;3x" : "3x+"} row.`,
          ],
        };
      }
      const m = mode === "clean" ? pick([1.5, 2, 2.5, 3, 4, 5]) : pick([1.65, 2.35, 2.85, 3.4, 4.2]);
      const irr = Math.pow(m, 1 / n) - 1;
      return {
        q: `You underwrite ${mx(m, m % 1 === 0 ? 0 : 2)} over ${n} years. What is the IRR?`,
        a: pct(irr),
        method: [
          `IRR = MoM<sup>1/n</sup> &minus; 1 = ${m}<sup>1/${n}</sup> &minus; 1`,
          `= <strong>${pct(irr)}</strong>`,
          `Anchors: 2x/3y = 26% &middot; 2x/5y = 15% &middot; 3x/5y = 25% &middot; 2.5x/4y = 26%`,
        ],
      };
    },
  },

  {
    id: "attribution",
    name: "Return attribution",
    bucket: "Return math",
    table: null,
    teaching:
      "Every equity return decomposes into exactly three multiplicative legs &mdash; growth &times; margin change &times; multiple change &mdash; plus buyback as a fourth. Compute each separately, then multiply. Never add. The real work is asking what the IRR becomes if you are wrong about the leg you are least sure of, which is almost always the margin.",
    gen(mode) {
      const g = (mode === "clean" ? pick([10, 12, 15, 20]) : pick([13.5, 16.4, 18.7])) / 100;
      const n = pick([3, 4, 5]);
      const [m0, m1] =
        mode === "clean" ? pick([[20, 30], [15, 25], [25, 32], [10, 18]]) : pick([[17.5, 26.4], [22.3, 29.1]]);
      const [x0, x1] = mode === "clean" ? pick([[22, 20], [25, 20], [30, 25], [18, 16]]) : pick([[23.5, 18.2], [27.4, 21.6]]);
      const gLeg = Math.pow(1 + g, n);
      const mLeg = m1 / m0;
      const xLeg = x1 / x0;
      const total = gLeg * mLeg * xLeg;
      const irr = Math.pow(total, 1 / n) - 1;
      const flat = gLeg * xLeg;
      const flatIrr = Math.pow(flat, 1 / n) - 1;
      return {
        q: `Revenue grows ${pct(g, mode === "clean" ? 0 : 1)} a year for ${n} years. EBIT margin goes ${m0}% &rarr; ${m1}%. The multiple goes ${x0}x &rarr; ${x1}x. What is your IRR?`,
        a: `${mx(total)} &rarr; ${pct(irr)} IRR`,
        method: [
          `Growth leg: ${(1 + g).toFixed(3)}<sup>${n}</sup> = <strong>${mx(gLeg)}</strong>`,
          `Margin leg: ${m1} &divide; ${m0} = <strong>${mx(mLeg)}</strong>`,
          `Multiple leg: ${x1} &divide; ${x0} = <strong>${mx(xLeg)}</strong>`,
          `Multiply: ${mx(gLeg)} &times; ${mx(mLeg)} &times; ${mx(xLeg)} = <strong>${mx(total)}</strong> &rarr; ${pct(irr)} IRR`,
          `Wrong-leg test &mdash; if margins never move: ${mx(flat)} &rarr; <strong>${pct(flatIrr)}</strong>. That floor is the number to underwrite.`,
        ],
      };
    },
  },

  {
    id: "drag",
    name: "De-rating drag",
    bucket: "Return math",
    table: T_DRAG,
    teaching:
      "This table is why expensive compounders disappoint. A 20% grower that de-rates 40% over three years nets about 4% a year. Over five years the same de-rate costs only ~10% a year &mdash; <em>duration is the antidote to multiple risk</em>, which is precisely the argument for a three-year holding period on a twelve-month-horizon book.",
    gen(mode) {
      const [x0, x1] = mode === "clean" ? pick([[25, 20], [30, 21], [40, 24], [25, 15], [35, 28]]) : pick([[27.4, 19.8], [33.1, 22.7]]);
      const n = pick([2, 3, 5]);
      const g = (mode === "clean" ? pick([10, 15, 20, 25]) : pick([13.2, 18.6])) / 100;
      const dragAnnual = Math.pow(x1 / x0, 1 / n) - 1;
      const total = Math.pow(1 + g, n) * (x1 / x0);
      const irr = Math.pow(total, 1 / n) - 1;
      return {
        q: `Earnings grow ${pct(g, mode === "clean" ? 0 : 1)} a year. Over ${n} years the multiple goes ${x0}x &rarr; ${x1}x. What is your annualised return?`,
        a: pct(irr),
        method: [
          `Multiple change: ${x1} &divide; ${x0} = ${(x1 / x0).toFixed(3)}, i.e. <strong>${pct(dragAnnual)}</strong> a year of drag`,
          `Earnings: ${(1 + g).toFixed(2)}<sup>${n}</sup> = ${mx(Math.pow(1 + g, n))}`,
          `Combine multiplicatively: ${mx(Math.pow(1 + g, n))} &times; ${(x1 / x0).toFixed(3)} = ${mx(total)} &rarr; <strong>${pct(irr)}</strong>`,
          `Note the additive shortcut (${pct(g)} ${dragAnnual < 0 ? "&minus;" : "+"} ${pct(Math.abs(dragAnnual))}) overstates by about ${Math.abs((g + dragAnnual - irr) * 100).toFixed(1)} points &mdash; that is the cross term.`,
        ],
      };
    },
  },

  {
    id: "incremental",
    name: "Incremental margin",
    bucket: "Margins & unit economics",
    table: null,
    teaching:
      "Incremental margin is the honest way to express operating leverage: revenue grows $100, EBIT grows $X. A margin ramp toward a target hides the assumption; an incremental margin states it. Always compare the implied incremental margin against what the company has actually delivered in prior growth years &mdash; if your model implies 50% and history says 30%, you are making a claim you need to name.",
    gen(mode) {
      const r0 = mode === "clean" ? pick([500, 800, 1000, 1200]) : pick([742, 1183, 1465]);
      const growth = (mode === "clean" ? pick([15, 20, 25]) : pick([17.4, 22.8])) / 100;
      const m0 = (mode === "clean" ? pick([15, 20, 25]) : pick([18.3, 23.7])) / 100;
      const inc = (mode === "clean" ? pick([30, 40, 50]) : pick([34, 43])) / 100;
      const r1 = r0 * (1 + growth);
      const e0 = r0 * m0;
      const e1 = e0 + (r1 - r0) * inc;
      const m1 = e1 / r1;
      return {
        q: `Revenue is ${money(r0)}m at a ${pct(m0, mode === "clean" ? 0 : 1)} EBIT margin. Revenue grows ${pct(growth, mode === "clean" ? 0 : 1)} and management says incremental margins are ${pct(inc, 0)}. What is the new EBIT margin?`,
        a: pct(m1),
        method: [
          `New revenue: ${money(r0)}m &times; ${(1 + growth).toFixed(3)} = ${money(r1)}m, so incremental revenue is ${money(r1 - r0)}m`,
          `Starting EBIT: ${money(r0)}m &times; ${pct(m0, 1)} = ${money(e0)}m`,
          `Incremental EBIT: ${money(r1 - r0)}m &times; ${pct(inc, 0)} = ${money((r1 - r0) * inc)}m`,
          `New EBIT ${money(e1)}m on ${money(r1)}m = <strong>${pct(m1)}</strong>, i.e. ${((m1 - m0) * 10000).toFixed(0)}bps of expansion`,
        ],
      };
    },
  },

  {
    id: "yield",
    name: "Multiples & yield",
    bucket: "Valuation",
    table: T_YIELD,
    teaching:
      "Flipping a multiple into a yield is the fastest way to make a valuation intuitive and to compare across asset classes. A 25x stock is a 4% earnings yield &mdash; ask immediately whether that yield grows, because a 4% yield growing 15% and a 4% yield growing 3% are entirely different securities wearing the same multiple.",
    gen(mode) {
      const kind = pick(["yield", "evs"]);
      if (kind === "yield") {
        const x = mode === "clean" ? pick([10, 12.5, 15, 20, 25, 30, 40]) : pick([17.4, 23.8, 31.2]);
        const y = 1 / x;
        const g = (mode === "clean" ? pick([5, 10, 15]) : pick([8.4, 12.6])) / 100;
        return {
          q: `A stock trades at ${x}x earnings and grows ${pct(g, mode === "clean" ? 0 : 1)}. What is the earnings yield, and what is it in three years if the multiple holds?`,
          a: `${pct(y)} today, ${pct(y * Math.pow(1 + g, 3))} on year-three earnings`,
          method: [
            `Earnings yield = 1 &divide; ${x} = <strong>${pct(y)}</strong>`,
            `Year-three earnings are ${mx(Math.pow(1 + g, 3))} today's, so the yield on cost is ${pct(y)} &times; ${mx(Math.pow(1 + g, 3))} = <strong>${pct(y * Math.pow(1 + g, 3))}</strong>`,
            `Same multiple, and the yield on your cost has moved ${((y * Math.pow(1 + g, 3) - y) * 100).toFixed(1)} points. That is what growth buys.`,
          ],
        };
      }
      const evs = mode === "clean" ? pick([4, 5, 6, 8, 10]) : pick([5.4, 7.3, 9.1]);
      const m = (mode === "clean" ? pick([20, 25, 30, 40]) : pick([23.5, 31.4])) / 100;
      const eve = evs / m;
      return {
        q: `A company trades at ${evs}x sales with a ${pct(m, mode === "clean" ? 0 : 1)} EBIT margin. What is the EV/EBIT?`,
        a: mx(eve, 1),
        method: [
          `EV/EBIT = EV/Sales &divide; margin = ${evs} &divide; ${m.toFixed(3)}`,
          `= <strong>${mx(eve, 1)}</strong>`,
          `Reverse it as a discipline: at a mature ${pct(m + 0.1, 0)} margin the same EV/Sales would be ${mx(evs / (m + 0.1), 1)} &mdash; which is what the bull case is really assuming.`,
        ],
      };
    },
  },

  {
    id: "expectations",
    name: "Implied expectations",
    bucket: "Valuation",
    table: null,
    teaching:
      "Reverse the question the market is answering. Rather than asking what a stock is worth, ask what has to be true for today's price to deliver your hurdle. It converts a vague sense that something is expensive into a specific, falsifiable claim about a growth rate &mdash; and it very often reveals that the required growth has never been achieved by anyone in the industry.",
    gen(mode) {
      const x0 = mode === "clean" ? pick([25, 30, 35, 40, 50]) : pick([27.6, 34.2, 43.8]);
      const x1 = mode === "clean" ? pick([15, 18, 20, 22]) : pick([16.4, 19.7]);
      const n = pick([3, 5]);
      const hurdle = (mode === "clean" ? pick([15, 20, 25]) : pick([17.5, 22.5])) / 100;
      const priceMult = Math.pow(1 + hurdle, n);
      const earningsMult = priceMult / (x1 / x0);
      const cagr = Math.pow(earningsMult, 1 / n) - 1;
      return {
        q: `A stock trades at ${x0}x earnings. You want a ${pct(hurdle, mode === "clean" ? 0 : 1)} annual return over ${n} years, and you assume it exits at ${x1}x. What earnings growth does that require?`,
        a: pct(cagr) + " a year",
        method: [
          `Price must compound to ${(1 + hurdle).toFixed(3)}<sup>${n}</sup> = <strong>${mx(priceMult)}</strong>`,
          `The multiple works against you: ${x1} &divide; ${x0} = ${(x1 / x0).toFixed(3)}`,
          `So earnings must do ${mx(priceMult)} &divide; ${(x1 / x0).toFixed(3)} = <strong>${mx(earningsMult)}</strong> over ${n} years`,
          `That is <strong>${pct(cagr)}</strong> a year. Now ask: has this company, or anyone in this industry, ever sustained that?`,
        ],
      };
    },
  },

  {
    id: "ev",
    name: "Expected value & asymmetry",
    bucket: "EV & sizing",
    table: null,
    teaching:
      "Expected value is easy; the discipline is being honest about the probability and checking the asymmetry separately. A position can have positive expected value and still be a bad idea if the loss case is large enough to force you out before the thesis resolves. Ask both questions: what is the EV, and what is the ratio of upside to downside.",
    gen(mode) {
      const p = (mode === "clean" ? pick([50, 60, 65, 70, 75]) : pick([57, 63, 72])) / 100;
      const up = (mode === "clean" ? pick([40, 50, 60, 80, 100]) : pick([47, 68, 84])) / 100;
      const down = (mode === "clean" ? pick([15, 20, 25, 30]) : pick([18, 27])) / 100;
      const ev = p * up - (1 - p) * down;
      const rr = up / down;
      const breakeven = down / (up + down);
      return {
        q: `You think there is a ${pct(p, 0)} chance the stock is up ${pct(up, 0)} and a ${pct(1 - p, 0)} chance it is down ${pct(down, 0)}. What is the expected value, and what probability would you need just to break even?`,
        a: `EV = ${pct(ev)}; breakeven probability ${pct(breakeven, 0)}`,
        method: [
          `EV = ${p.toFixed(2)} &times; ${pct(up, 0)} &minus; ${(1 - p).toFixed(2)} &times; ${pct(down, 0)} = <strong>${pct(ev)}</strong>`,
          `Risk/reward = ${pct(up, 0)} &divide; ${pct(down, 0)} = <strong>${rr.toFixed(1)} to 1</strong>`,
          `Breakeven probability = downside &divide; (upside + downside) = <strong>${pct(breakeven, 0)}</strong>`,
          `So you have ${((p - breakeven) * 100).toFixed(0)} points of cushion on the probability estimate. That margin, not the EV, is what should drive the size.`,
        ],
      };
    },
  },
];
