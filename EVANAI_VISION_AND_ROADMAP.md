# EvanAI Vision and Roadmap

Decision memo for a meeting tonight. 100B from scratch is a gated ambition, not the ask.

**Tonight's ask:** fund a leakage audit of the existing stack and a small point-in-time world-model proof. Do not fund a 100B training run.

All dollar figures are planning assumptions, not live quotes. Vault citations (`wiki/…`) come from the retrieved evidence packet, not files in this repo.

---

## 0. Tonight card

**One sentence.** EvanAI is a market world model: current state, moving parts, what happens if something changes — then a trade. It is not a model that guesses tomorrow's close.

**Status.** We already have a backtest and options harness. We do not know if the last distilled checkpoint had an edge. We freeze it and audit whether it saw the future. We do not throw the harness away.

**Trap we will not walk into.** Training on stories we wrote, then celebrating a high score. That is practice. Real tape is the exam.

**If asked “how much for 100B.”** One clean dense 100B pretrain on ~2T tokens is about 830k H100-hours: **~$1.7M–$4.2M** at assumed $2–$5/GPU-hour, **~34 days on 1,024 H100s at the assumed 40% utilization**. Data generation for 8TB can cost as much as or more than the clean training run. Compute-plus-data for a 100B-dense program is **~$4.1M–$11.2M**. A fully loaded planning allowance (engineering, evaluation, inference, and failed runs) is **$10M–$50M**, pending vendor and staffing validation. None of that is tonight's check.

**First proof.** One clean 1B–3B pretraining run is approximately **$170–$3.8k** of assumed GPU time. The complete proof also requires data, engineering, ablations, and evaluation. Phases 0–2 take roughly 4–7 months if run sequentially.

**Do not say:** Leopold made $25B; the old model is useless; we will not miss free opportunities; high synthetic win rate means we are ready; one GPU plus an SSD trains 100B.

---

## 1. The plan, stated clearly

A forecast model asks: will this stock go up.

A world-dynamic model asks: what is the current state of the system, what are the moving parts, and what happens if one of them changes.

Forecast: “the factory stock might go up next month.”
World-dynamic: “this factory depends on one chip supplier. If that supplier shuts down, production drops, customers scramble, rivals with extra inventory get stronger.”

The product is software that sees that chain early enough to act: long, short, or option; how long to hold; how much of the fund to put on it. Abstention is a valid action. A correct causal story can still be a no-trade if it is already priced, the timing is mush, or the available options are too expensive.

The 2021 compute/MoE chain and the 2025 coding-agent / memory chain are examples of the *class* of bet: public facts, a chain most people did not size, a trade that required connecting dots rather than reading the next close. They are illustrations. They are not the final test. They influenced this design, so they cannot be the concealed exam.

Four questions stay separate modules:

1. **World state.** What companies, products, suppliers, customers, inventories, policies, technologies, and market expectations exist at time `t`?
2. **Dynamics.** If an event occurs, how could that state change over several horizons?
3. **Trade selection.** Which instrument expresses it: stock, call, put, short, spread, or no trade?
4. **Portfolio sizing.** How much risk, after uncertainty, liquidity, correlation, existing exposure, and loss limits?

A model can get (1) and (2) right and still correctly output “no trade.”

### What “opportunity” means

An opportunity is not a stock that later went up.

An opportunity exists when, using only information available at a historical cutoff:

- A specific causal thesis can be stated.
- At least one liquid instrument could express it.
- The predicted outcome has positive expected value after spreads, fees, borrow, option decay, and estimated impact.
- It fits portfolio risk limits.
- It has a falsification condition and an expected horizon.

Each benchmark opportunity records:

```text
information_cutoff
entities_and_dependencies
observable_trigger
causal_thesis
expected_outcomes_and_probabilities
instrument
direction
entry_window
holding_horizon
invalidating_event
maximum_risk
realized_outcomes
```

“Never miss a free opportunity” is not a spec. There is no free opportunity. The practical target is higher recall on identifiable dislocations at a controlled false-positive and risk budget.

---

## 2. Row, label, cutoff

Three definitions used throughout this plan.

**Row.** One decision moment. What the model is allowed to see at that moment, and nothing later.

**Label (Y).** The answer you grade for that row. Not “the price.” For real rows, labels grade observable outcomes after the cutoff: did the structure emerge, and did each cutoff-valid instrument make money after costs? Real history reveals only the branch that happened. Counterfactual labels exist only in controlled experiments or synthetic simulators where both branches are defined.

**Cutoff.** Train only on rows whose *availability time* is before the test period. Random splits are invalid. If Tuesday’s news is in the training set, you cannot test Monday.

Example row:

```text
Cutoff: 2021-03-31 16:00 ET
Inputs X: filings, news, prices, option quotes, supply-chain facts, estimates
          that were publicly available by that cutoff
Labels Y: what happened after the cutoff
```

EvanAI needs a label vector, not one up/down bit:

```text
Y = {
  state_changes,
  event_occurrence,
  return_distribution_by_horizon,
  volatility_and_drawdown,
  maximum_favorable_and_adverse_excursion,
  executable_return_after_costs,
  thesis_invalidation
}
```

Every input carries two clocks plus provenance:

- `event_time` — when the thing happened
- `available_at` — earliest instant a trader could have known it
- `source`, `revision/version`, `entity`, `synthetic_or_real`

Training uses `available_at`, not a database’s current contents. Restated fundamentals, amended filings, delisted names, future index membership, and later-written summaries otherwise leak the answer.

Records missing a valid availability stamp are refused, not defaulted. Retrieval enforces `available_at <= decision_cutoff` in the query layer.

Training stores learned patterns in weights. That is normal. The failure is when a row contains the future.

Weights are not a database. Retrieval supplies specific, current records when the model is used. Synthetic examples may be used during training, but they do not become a separately addressable database inside the weights.

---

## 3. Verdict

**Keep.** The world-dynamic objective. State, mechanisms, conditional scenarios, then trade. Markets reflect interacting mechanisms and expectations. A model aimed at suppliers, bottlenecks, and what changes is doing a different job than next-price prediction.

**Do not keep as the plan.** 100B from scratch as the first move. 8TB of DeepSeek-written markets as the training set, the labels, and the final exam. “High success on markets we made up means we are ready.” “Put synthetic markets into the weights” as a separate memory trick. “The old model is useless.” “We will not miss free opportunities.”

Why the plan as stated fails:

1. **Synthetic success is not real-market edge.** You wrote the story and know the ending. A high synthetic win rate establishes performance inside that simulator, not transfer to real markets. Evaluation details matter: the live options harness showed 123 winners under EOD semantics versus 111 under minute-level entry semantics, and 17 EOD winners disappeared (`wiki/agentic-trading-system.md:85-91`).
2. **DeepSeek agents are one prior, sampled many times.** Repeated samples from one model have correlated failure modes and are not independent corroboration. Count distinct providers, not requested profiles (`wiki/model-fusion.md:23-47`).
3. **Hindsight is already in the teacher.** A generator trained after 2025 may know the named outcomes. Synthetic “missed opportunities” can leak the answer in the prose, causing the student to learn hindsight cues instead of a transferable mechanism.
4. **100B does not fit “an SSD and a GPU.”** Inference weights alone are ~200GB in bf16 (model-knowledge). Training memory is ~1.6TB including optimizer states (assumed 16 bytes/param). Pretrain is a cluster job. 100B is Phase 6, gated.
5. **“Won’t miss free opportunities” is not measurable.** Higher recall at a controlled false-positive budget is.

The prior stack is not proven to make money. That is a different sentence from “throw it away.”

---

## 4. Prior stack: leakage audit, not disposal

What was said: distilled Qwen, frameworks, backtest harness, news; unsure if it made money; prices are in the weights; maybe useless.

What to do: quarantine the checkpoint. Audit. Keep the machinery.

### Why “prices in the weights” is not automatic death

Language models store what they trained on. If the only issue is “it saw historical prices,” that is ordinary training. It may still be a weak *forecaster* because prices are non-stationary. The killing issue is **leakage**: future prices, future news, or restated fundamentals sitting in rows dated earlier than they were knowable.

Until that is measured, you cannot say the checkpoint is dead and you cannot say it works.

### Audit

- Rebuild a sample of training rows with both clocks.
- Ask the checkpoint questions with a frozen cutoff. If it uses facts from after the cutoff, it leaked.
- Compare backtest winners under EOD vs executable fills. A result that ignores executable entry conditions is not credible execution-adjusted P&L (`wiki/agentic-trading-system.md:85-91`).
- Time-travel canary: inject records with future `available_at`; if they appear in an `as_of=T` load, the pipeline fails.

### Keep

| Keep | Why |
|---|---|
| Backtest harness, options gates, spread/fill rules | This is the eval layer. The human 300-winner gate remained closed; that honesty is an asset (`wiki/agentic-trading-system.md:85-91`). |
| Point-in-time crawl / banked ticker-days | Raw material for a leakage-audited dataset. |
| Prediction-market scans and preregistered promotion | Same discipline the new model needs (`wiki/agentic-trading-system.md:75-79`). |
| Volume and quality together as the product goal | Measure opportunity recall and winner quality separately rather than trading one away. |

### Quarantine

| Quarantine | Why |
|---|---|
| Distilled Qwen checkpoint | Unknown leakage, unknown live edge. Do not train further on it until the audit. |
| Any “it was making money” story | Not measured. Do not pitch it. |

---

## 5. Architecture

### M1 — Point-in-time evidence layer

Real market evidence with provenance: filings and amendments, earnings calls, news with publication timestamps, fundamentals as originally published, products/facilities/suppliers/customers/competitors, policy and macro events, stocks/options/borrow/rates/corporate actions, revision histories, delisted companies.

Retrieval must enforce `available_at <= decision_cutoff`.

Initial storage option: versioned Parquet datasets queried through DuckDB, with explicit `event_time` and `available_at` filters. This is an implementation proposal, not an existing EvanAI dependency. Real and synthetic data live in separate namespaces. No untagged mixed shard.

### M2 — Entity and dependency graph

```text
company -> depends_on -> supplier
product -> consumes -> component
customer -> purchases_from -> company
factory -> produces -> product
policy -> constrains -> industry
competitor -> substitutes_for -> company
```

Each edge carries confidence, sources, validity dates, and uncertainty.

### M3 — World-state encoder

Latent market state `z_t`: capacity and bottlenecks, demand and inventories, capex, technology adoption, competitive position, financing, market expectations, and uncertainty at real time `t`. It is compressed working memory, not a database replacement.

### M4 — Dynamics and intervention model

```text
p(z_(t+h) | z_t, event_or_intervention, evidence)
```

Distributions over future states, not one certain story. Historical observational data cannot prove every causal arrow. These are conditional scenarios.

### M5 — Opportunity detector

Compares predicted future states with contemporaneous market expectations. Expectations are represented through point-in-time observable proxies such as price, implied volatility, analyst estimates, consensus forecasts, and positioning proxies; they are not treated as a directly observed hidden variable. Is the consequence already reflected? How large is the disagreement? What evidence would close it? Output: thesis, probability distribution, timing, supporting and contradictory evidence, confidence.

### M6 — Instrument and trade policy

Maps a qualified opportunity to long/short equity, calls/puts, defined-risk spreads, relative-value, or no trade. Evaluates strike, expiry, implied volatility, borrow, liquidity, catalyst timing, and loss profile. It must be allowed to abstain.

### M7 — Portfolio allocator

Separate from thesis generation. Inputs: candidate return distributions, calibration, correlations, existing exposures, liquidity, drawdown limits, tail scenarios. A deterministic risk engine can override the model.

### M8 — Execution and monitoring

Recommendation-only and shadow trading first. Simulation must include latency, spread, depth, partial fills, impact, option quote staleness, borrow, exercise/expiry/corporate actions, fees, rejects. This is material: EOD vs minute already changed the winner set (`wiki/agentic-trading-system.md:85-91`).

World model, trade policy, portfolio allocator, and risk engine remain separate. No autonomous live retraining from recent P&L without a new frozen evaluation.

### Training stages (once data exists)

- **TR1** Representation: entity resolution, event order, source grounding, temporal retrieval, dependency prediction.
- **TR2** Historical state transitions at multiple horizons. Calibrated distributions, not persuasive prose.
- **TR3** Counterfactual branches on known mechanisms. Synthetic, tagged, never in the final real-market test set.
- **TR4** Opportunity learning, including negative cases that were already priced or never happened. Trade-policy and sizing models train on out-of-fold world-model predictions, meaning predictions for rows the world model did not train on. In-sample predictions would give downstream policies unrealistically clean signals.
- **TR5** Trade policy against executable outcomes after costs. Generate outcomes for every instrument that was actually available and liquid at the cutoff. Never select the best contract after observing the future. Keep this separate from world-state accuracy so failure can be attributed to reasoning, timing, instrument, or execution.
- **TR6** Portfolio policy only after forecasts are calibrated. Constrained utility using cutoff-valid correlations and exposures, not raw simulated profit.
- **TR7** Recurrent updates of private reasoning state `r_{t,k}` before an answer. Structured auxiliary supervision. Natural-language rationale is an audit output, not proof the hidden computation used it.

---

## 6. Data: real tape and synthetic drills

### Real data — two-clock pipeline

Failure modes to block:

- **FM-A1** Vendor backfill. Store original and revision. Train on as-published originals.
- **FM-A2** Survivorship. Point-in-time universe snapshots, including delistings.
- **FM-A3** Derived-feature lookahead. Transforms fit only on `available_at <= T`.
- **FM-A4** Timestamp misalignment. UTC plus raw stamp retained.

Corpus: equities and options (EOD plus minute depth where licensed — minute depth is required because winner sets changed under realistic liquidity), corporate actions, point-in-time index membership, fundamentals as-filed, filings with EDGAR acceptance times, timestamped news, macro vintages, supply-chain graph.

### Split discipline

Time separation is necessary but not sufficient. Group related events, issuers, suppliers, and overlapping label horizons so the same causal episode cannot leak across splits. Random ticker splits alone are invalid because time, related entities, and overlapping events can still cross the boundary. Purge or embargo rows whose outcome horizon crosses a split.

Evaluation partitions:

- **Train and development:** early chronological data.
- **Validation:** a later period used for model and threshold decisions.
- **Retrospective challenge set:** periods already inspected by the team, including the named 2021 and 2025 examples. These are diagnostics, never concealed evidence.
- **Sealed historical holdouts:** positive and negative cases selected and access-controlled by an independent evaluator. Each holdout is used once for one promotion decision, then retired.
- **Prospective holdout:** decisions made after the model, retrieval system, thresholds, and risk rules are frozen.

Every evaluation query is logged. Reusing a sealed holdout to choose the next model causes holdout rot.

### Synthetic markets — drills, not the scoreboard

Synthetic markets are not evidence of real-market edge. High synthetic success establishes performance on the generator and simulator distribution, not transfer. Their real value:

1. Exact simulator-defined causal labels for mechanisms encoded by the simulator. These labels are not guaranteed to describe real-market causality.
2. Dense coverage of rare regimes.
3. A reward verifier for reasoning training.

Transfer to untouched real tape is a hypothesis. It is never assumed.

**Division of labor.** An LLM paints the canvas (entities, networks, and news consistent with the current state). A rules-based simulator computes outcomes from an explicit causal dependency graph (DAG). If the LLM writes both story and outcome, hindsight is baked in.

**Counterfactual branches.** Same initial state; shock applied / not applied / varied magnitude and timing. The model learns `P(outcome | state, intervention)`. The simulator ran both branches, so the causal label is known, not inferred.

**Contamination controls.**

- Fictional namespace. No real tickers, company names, or dates. Blocklist plus entity registry.
- Mechanism banks, not retellings of 2021/2025. Parameterized families: single-supplier, capacity constraint, demand shock, overbuild, regulatory shift, financing squeeze. Flag scenarios whose structure correlates too highly with documented real episodes for separate review.
- Symmetric boom and bust branches per mechanism.
- Decontamination scan for real entities, dates, and price series near real history.

**Generator diversity.** Multiple DeepSeek agents are one model sampled many times (`wiki/model-fusion.md:23-47`). Diversity comes from mechanism families, simulator regimes, seeds, and additional generator families when actually keyed. If only DeepSeek is live, every shard carries a `single-generator` flag and reporting counts distinct generators, not generation runs. Temperature is not diversity.

**Refinement.** Schema validation, DAG-consistency tests, liquidity realism using the same 15-minute entry window / spread-reject / median-fill rules as the real harness (`wiki/agentic-trading-system.md:85-91`), near-duplicate dedup, contamination scan, balance audit, provenance-tagged tokenization.

### Simulator limitations (do not soften)

- **L1** Authored dynamics. Rules cover what we wrote. Real markets add reflexivity and regime shifts. Maximizing synthetic reward can mean learning the rules.
- **L2** Injected liquidity. Fills are only as honest as the injected spread model.
- **L3** LLM-shaped news is not adversarial the way real news is.
- **L4** No social dynamics. The reason “obvious” trades were hard to hold is absent.
- **L5** Unknown unknowns. Mechanisms outside the bank never occur. Hold entire mechanism families out of training for evaluation E2 below.

---

## 7. Neuralese, in a stock-market sense

The request was: the model speaks to itself through the transformer in its own wording.

That sentence as ticker-English self-talk is chain-of-thought with extra branding. It is not a training method.

**What can work.** Keep two clocks separate. `z_t` is the market state at real time `t`. `r_{t,k}` is the model's private reasoning state at internal step `k`:

```text
r_(t,k+1) = f(r_(t,k), z_t, retrieved_evidence)
```

The recurrent state is carried as vectors and trained to retain what future predictions need. Analogues in the literature (model-knowledge, not a claim we have implemented them) include continuous latent thought, recurrent depth, and GRU/Transformer-XL-style state. The model need not emit English between internal steps. It updates `r_{t,k}`, then decodes a structured belief and trade.

**Self-talk with a receipt.** Selected reasoning checkpoints have auxiliary decoders that produce typed objects. The private recurrent state does not need to emit English or a complete object at every step:

- `state_summary`: entities, dependency edges, regime (fixed taxonomy)
- `hypotheses[]`: mechanism family, instruments, direction, horizon, confidence
- `counterfactuals[]`: if-X-then-Y-else-Z tied to the DAG
- `decision`: instrument, structure, size, entry/exit, max loss
- `expected_evidence`: what should be observed next if the hypothesis is true

Natural-language rationale is an audit output. It is not proof the hidden computation used it.

**Reward (simulator as verifier, then real tape as exam).**

- Calibration first. Brier/log on defined observables. Not raw P&L.
- Counterfactual branch discrimination against simulator ground truth.
- Decision utility after costs, drawdown-penalized and liquidity-capped, with adversarial or worse-than-mid fill sampling in synthetic worlds.
- Process: expected-evidence checks at `t+1`, so lucky guesses do not get a free pass.
- STaR-style iteration (model-knowledge): keep traces that were calibrated and correct, fine-tune, repeat. This sharpens in-distribution reasoning. It creates no new real-market information.
- Anti-hacking: reward caps per mechanism family; audit top-decile traces. Canary scenarios containing deliberate simulator faults remain outside training and test whether the model exploits simulator artifacts.

**Neuralese failure modes.**

- **FM1** `r_{t,k}` encodes generator style. Test: train on generator A, evaluate on generator B.
- **FM2** Simulator exploitation. Use held-out canaries and adversarial fill assumptions.
- **FM3** Decorative structure. If removing the structured channel does not affect decisions, it is not decision-critical. Faithfulness requires additional interventions on latent state and checks that predictions change as expected; ablation alone measures utility.
- **FM4** Synthetic overconfidence. Report real-holdout calibration separately. Never blend.

---

## 8. How we know it worked

### Transfer ladder (preregister before claiming simulator success)

Same discipline as existing preregistered forward promotion (`wiki/agentic-trading-system.md:75-79`).

- **E1** In-distribution synthetic holdout. Expected pass. Proves little.
- **E2** Held-out mechanism families. Generalization beyond memorized mechanisms.
- **E3** Cross-generator. Tests canvas-style leakage and FM1. All synthetic rungs still share authored simulator rules, so simulator-rule overfitting is detectable only at E4.
- **E4** The next sealed real holdout, point-in-time only, scored on calibration and recall/precision against preregistered dislocations, with fills charged through minute-level liquidity gates (`wiki/agentic-trading-system.md:85-91`). Gate-deciding models and baselines must have a documented corpus cutoff before the holdout. Pretrained systems whose corpus cutoff is unknown or overlaps the holdout are reported separately and excluded from promotion decisions. At-or-below the strongest eligible baseline means stop.
- **E5** Prospective shadow trading. Live paper. Preregistered duration and criteria. No retraining mid-test.

**Promotion rule.** No scale-up beyond the 3B class until E4 clears baselines with margins stated in advance. 30B and 100B follow the gates in §9.

**Failure pivot, stated now.** If E2 passes and E4 fails, synthetic training did not demonstrate real-market transfer. Keep the point-in-time pipeline and structured outputs. Drop the transfer claim.

### Frozen evaluation structure

1. Develop on an early historical interval.
2. Tune on a later validation interval.
3. Lock model, prompts, retrieval, opportunity definition, and metrics.
4. Evaluate once on the next sealed chronological block and retire it.
5. Hold out industries and causal chains as additional transfer tests.
6. Purge and embargo boundary periods where labels overlap.
7. Run a frozen prospective shadow book for 3–6 months without mid-test retraining.

Hand-selected missed opportunities are diagnostic. They are not the sole benchmark.

### Baselines

- **Forecast and opportunity:** simple event rules, momentum, earnings revisions, news sentiment, retrieval plus a general-purpose model, the existing Qwen where its corpus cutoff permits, and architecture ablations without dynamics, synthetic data, or recurrent state.
- **Portfolio:** cash, buy-and-hold, risk-matched index exposure, and simple long/short strategies.

### Metrics

- **Recall:** fraction of benchmark opportunities found within the fixed review budget.
- **Precision:** fraction of generated alerts that satisfy the benchmark definition.
- **Brier score:** error in predicted probabilities; lower is better.
- **Calibration:** whether outcomes predicted at 70%, for example, happen about 70% of the time.
- **Ablation:** remove one component and measure what changes.
- **Block bootstrap:** estimate uncertainty while preserving clusters of nearby market observations.

World-model: event log loss or Brier score, calibration by confidence bucket, state-variable error, dependency and temporal-order accuracy, intervention consistency, contradictory-evidence sensitivity.

Opportunity: recall and precision at a fixed analyst-review budget, lead time before repricing, false-positive cost, and results by regime, sector, and horizon.

Trading: net return after executable costs, risk-adjusted return, maximum drawdown, turnover, tail loss, liquidity and capacity, hit rate by confidence, and attribution across model, policy, sizing, and execution. Report distributions and block-bootstrap intervals, not one aggregate return.

### Risk controls

Hard issuer, sector, factor, gross, net, leverage, and option-premium limits. Max loss per thesis and per day. Liquidity and participation limits. Borrow and option-quality gates. Abstention below confidence. Human approval through shadow and first live. Independent kill switch. Immutable decision logs of evidence available at cutoff. Drift monitors. Stress tests for correlated thesis failure. Data-license, manipulation, MNPI, and compliance review.

---

## 9. Roadmap

Assumptions: liquid US equities and listed options; days-to-months horizon, not high-frequency; legally obtained public or licensed data; first deployment is recommendation-only; 100B is optional scale, not an architectural requirement.

### Phase 0 — Define and audit (2–4 weeks)

Opportunity spec, training-row schema, point-in-time rules, leakage audit of the old checkpoint and datasets, inventory of reusable retrieval/backtest/options/execution pieces, preregistered metrics and baselines.

**Gate G0.** Every benchmark record has a traceable cutoff and label rule. The old system can be evaluated without contaminating new holdouts. No unresolved high-severity leakage remains in any component used for evaluation; affected components are excluded until repaired.

### Phase 1 — Data and benchmark MVP (6–10 weeks)

Bitemporal real-data store, entity graph, positive/negative/already-priced cases, frozen validation and concealed test manifests, executable equity and options simulator, baseline results.

**Gate G1.** Provenance and availability timestamps exist for 100% of included benchmark inputs. Automated cutoff tests pass. A preregistered manual audit sample contains zero high-severity post-cutoff records. Delistings and corporate actions are represented, and baselines reproduce from immutable manifests.

### Phase 2 — Small-model proof (8–12 weeks)

Train a 0.3B–3B scratch model on the proposed objective, plus a comparable pretrained or continued-pretraining baseline and ablations without dynamics or synthetic data. A pretrained baseline is gate-eligible only when its corpus cutoff predates the evaluation period; otherwise report it separately.

**Gate G2.** Before training, fix review budget `K`, the precision floor, harm bounds, and corpus cutoff for every candidate and baseline. Pass only if Brier skill and recall-at-`K` differences versus the strongest eligible baseline both have positive 95% block-bootstrap lower bounds, the precision floor is met, and no critical regime or sector breaches its harm bound. Synthetic-only improvement does not qualify.

### Phase 3 — World dynamics and scenario engine (8–16 weeks)

Latent state-transition model, counterfactual generator, structured reasoning supervision, trade-policy prototype, mechanism tests.

**Gate G3.** The preregistered dynamics metric and opportunity metric on a newly sealed real test both show positive uncertainty-adjusted improvement over the non-dynamics ablation. Generated scenarios improve real-data transfer, not only simulator scores; otherwise the gate fails.

### Phase 4 — Frozen shadow trading (3–6 months)

Freeze model, retrieval, policy, thresholds, and risk rules before starting.

**Gate G4.** Before shadow trading, use a power analysis to set the effective sample size needed to detect the target edge, then fix the execution-cost model, maximum drawdown, calibration band, uncertainty threshold, and risk-breach limit. Pass only if execution-adjusted expectancy clears that threshold, no hard risk limit is breached, and no single position or regime explains the result.

### Phase 5 — 7B–30B scaling study

Multiple sizes, same data and eval suite.

**Gate G5.** Fit the scaling relationship on at least three model sizes under one protocol, then require a held-back fourth size to support the projection. Data quality must hold at larger volume, gains must come from sealed real tests, and projected value over the best smaller model must exceed a predetermined investment hurdle after training and serving costs.

### Phase 6 — 100B decision

Choose dense versus MoE only after measured scaling curves exist.

**Gate G6.** Authorize 100B only if G0–G5 passed, independent evaluation reproduced the result, prospective shadow passed, data licensing and cluster capacity are secured, failure and rerun budgets are funded, and the projected benefit over the best smaller model justifies full program cost.

Calendar from today to a completed G4 is more like **12–24 months** of program time than the pretrain wall-clock. Pretrain duration is the short part.

**Immediate funding target:** Phases 0–2 (audit, point-in-time benchmark, small-model proof). Not Phase 6.

---

## 10. Compute, cost, and time

**Assumptions (not live quotes).** Reference GPU: H100 SXM 80GB, bf16. Peak ≈ 1.0e15 FLOP/s (model-knowledge, rounded from 9.89e14). MFU, or model FLOPs utilization, is the fraction of theoretical GPU throughput achieved by training. Baseline MFU is 40% → 4.0e14 FLOP/s effective. Dense training FLOPs = `6 × N × D`. MoE FLOPs use active parameters as an idealized approximation and exclude routing, communication, load-balancing, and expert-capacity overhead. Memory uses total parameters × ~16 bytes. The dense-model data heuristic is ~20 tokens/parameter. 8TB text ≈ 2.0e12 tokens at 4 bytes/token (range ~1.6T–2.7T at 5–3 bytes/token). GPU-hour rates are assumed **$2–$5**, baseline **$2.50**.

These are engineering scenarios. The arithmetic was independently recomputed from `6ND`, 4.0e14 effective FLOP/s, and 3600 seconds/hour.

### Clean pretrain scenarios (dense rows use 20 tokens/parameter; MoE rows consume a fixed 2T-token corpus; 40% MFU)

| Stage | Params | Tokens | FLOPs | GPU-hours | Cost @ $2.50 | Range @ $2–$5 |
|---|---|---|---|---|---|---|
| 1B dense | 1e9 | 2e10 | 1.2e20 | 83 | $208 | $167–$417 |
| 3B dense | 3e9 | 6e10 | 1.08e21 | 750 | $1,875 | $1,500–$3,750 |
| 30B dense | 3e10 | 6e11 | 1.08e23 | 75,000 | $187,500 | $150k–$375k |
| 100B dense | 1e11 | 2e12 | 1.2e24 | ~833k | ~$2.1M | $1.67M–$4.17M |
| 100B MoE, 10B active | 1e11 total | 2e12 | 1.2e23 | ~83k | ~$208k | $167k–$417k |
| 100B MoE, 20B active | 1e11 total | 2e12 | 2.4e23 | ~167k | ~$417k | $333k–$833k |

Spot-check: 6 × 1e11 × 2e12 = 1.2e24; ÷ (4.0e14 × 3600 = 1.44e18) ≈ 833,333 GPU-hours before rounding.

**MoE cuts idealized compute 5–10× in these fixed-corpus scenarios, not memory.** The MoE rows assume the entire 2T-token corpus is consumed regardless of active parameter count; they are not labeled compute-optimal. A 100B-total MoE with 10B active still stores 100B parameters. The cluster floor needed to fit the model does not shrink.

### Wall-clock, clean run, 40% MFU

| Stage | GPU-hours | 8 GPUs | 64 | 256 | 512 | 1,024 | 8,192 |
|---|---|---|---|---|---|---|---|
| 1B | 83 | 10.4 h | — | — | — | — | — |
| 3B | 750 | 3.9 d | 12 h | — | — | — | — |
| 30B | 75,000 | — | 49 d | 12.2 d | 6.1 d | 3.1 d | — |
| 100B dense | ~833k | — | — | 135 d | 68 d | 34 d | 4.2 d |
| 100B MoE 10B active | ~83k | — | 54 d | 13.6 d | 6.8 d | 3.4 d | — |

Formula: `days = GPU-hours ÷ cluster ÷ 24`. Spot-check before rounding: 833,333 ÷ 1,024 ÷ 24 ≈ 33.9 days.

### Memory floor (fitting, not timeline)

| Stage | Training memory (~16 B/param) | Practical cluster |
|---|---|---|
| 1B | 16 GB | 1–8 |
| 3B | 48 GB | 2–8 |
| 30B | 480 GB | 16–64 |
| 100B dense or MoE | 1.6 TB | 64–256 |

One GPU plus one 8TB SSD can hold data. It cannot train 100B.

### Sensitivity (100B dense, clean run)

| Lever | Low | Baseline | High |
|---|---|---|---|
| GPU-hour rate | $1.5 → $1.25M | $2.5 → ~$2.1M | $4.0 → $3.33M |
| MFU | 50% → 667k hrs ($1.67M) | 40% → 833k (~$2.1M) | 30% → 1.11M hrs ($2.78M) |
| Tokens/param | 10× → 1T ($1.04M) | 20× → 2T (~$2.1M) | 60× → 6T ($6.25M) |

Tokens per parameter is the largest lever. At the stated bytes-per-token assumption, 8TB ≈ 2T tokens and matches the 20-token-per-parameter dense-model heuristic for 100B. Training past that heuristic needs more than 8TB.

### 8TB synthetic generation (separate from training)

- **API path** (assumed $0.5–$3 per million output tokens): 2e12 tokens → **$1.0M–$6.0M**. At 1M tokens/s aggregate ≈ 23 days; at 100k/s ≈ 231 days. Needs a real fleet, not a handful of agents.
- **Self-host path:** assuming 5k–20k generated output tokens per GPU-second, 28k–111k GPU-hours → **$70k–$280k** at $2.50. Actual throughput depends on the generator architecture, precision, batching, and sequence length.
- **Judge/refine pass:** add ~1–2× raw generation.

8TB generation is a first-class cost. Under the API path it can exceed the training run.

Raw local storage acquisition for 8TB plus checkpoints may be roughly $1k–$3k. This excludes redundancy, backup, and the high-throughput storage needed to feed a cluster.

### Failed runs and program totals (compute + data)

Clean pretrain is not the bill. Ablations, restarts, post-training, eval ≈ 1.5–2.5× the clean run.

| Program target | Clean run | + overhead | + data gen | Compute + data |
|---|---|---|---|---|
| To 30B gate | $187k | $280k–$470k | $70k–$280k | **$350k–$750k** |
| To 100B dense | ~$2.1M | $3.1M–$5.2M | $1.0M–$6.0M | **$4.1M–$11.2M** |
| To 100B MoE 10B active | $208k | $312k–$520k | $1.0M–$6.0M | **$1.3M–$6.5M** |

Fully loaded program including engineering, evaluation infrastructure, and inference: use **$10M–$50M** only as a planning allowance pending vendor and staffing validation. It is not derived from the compute table.

**What to say tonight.** One clean small-model training run costs hundreds to thousands of dollars in assumed GPU time; the complete proof costs more because it includes data, engineering, ablations, and evaluation. A path to the 30B gate is roughly **$350k–$750k** compute plus data. A 100B dense commitment is a separate gated **~$2M+** clean run, **~$4M–$11M** compute-plus-data program, and **$10M–$50M** fully loaded planning allowance. Do not write the 100B check until G0–G5 pass.

---

## 11. Claims we will not make

| Code | Claim | Why it is out |
|---|---|---|
| U1 | Leopold / Situational Awareness Fund made $25B | Unverified. Use the class of structural public bets, not that number. |
| U2 | The old model is useless | Leakage unmeasured. Harness is reusable. |
| U3 | We will not miss free opportunities | Impossible spec. No “free.” |
| U4 | High synthetic win rate means the model is ready | Circular. Simulator skill is not evidence of real-market edge. |
| U5 | Prices in weights ⇒ must train 100B from scratch | Wrong diagnosis. Audit first. Scale only if small models fail for capacity reasons. |
| U6 | One GPU + 8TB SSD trains 100B | False. Cluster job. |
| U7 | Writing markets into weights is a separate memory trick | Training is weight updates. Else retrieval. |
| U8 | DeepSeek agent fleet = diverse world models | One provider, many samples (`wiki/model-fusion.md:23-47`). |
| U9 | Guaranteed return, guaranteed discovery, or live P&L from the prior harness | Not in evidence. Winner gate was closed (`wiki/agentic-trading-system.md:85-91`). |
| U10 | Neuralese = the net talks to itself in ticker English | Private state `r_{t,k}` plus structured auxiliary decoders. Language is the receipt, not the computation. |

None of U1–U10 appear in the pitches below.

---

## 12. Three pitches

Shared spine:

1. World-dynamic, not next price.
2. Catch structural dislocations, then size long / short / option, or stand down.
3. Existing harness is the test bench, not trash.
4. Synthetic markets are drills, not the scoreboard.
5. 100B is gated. Tonight’s ask is the first proof.
6. None of U1–U10.

### Pitch for technical people

We are building a point-in-time market world model: entities, dependencies, regime, counterfactual transition `p(z_{t+h} | z_t, intervention)`, then a separate trade and sizing head. Next-token price prediction is the wrong objective. The tape is non-stationary. The valuable bit is the causal chain, not the close.

A training row is one cutoff. Inputs may only include records with `available_at <= cutoff`. Labels are a vector: state changes, event occurrence, executable return after costs, invalidation. Random splits are invalid.

Immediate work is a leakage audit of the current checkpoint and a frozen-cutoff evaluation. Synthetic scenarios stress known mechanisms with simulator-defined labels inside a rules-based system. The LLM does not get to write the outcomes. Promotion requires transfer onto untouched real tape, executable fills, and a prospective shadow book. Market state `z_t` and private recurrent reasoning state `r_{t,k}` form the neuralese analogue: compressed vectors with structured receipts, not English self-talk. Ablations test whether the channel adds value; latent-state interventions test whether the receipt is faithful.

100B dense from scratch is a later scale gate: `6ND` ≈ 1.2e24 FLOPs, ~833k H100-hours, **~$1.7M–$4.2M** for one clean run at assumed $2–$5/GPU-hour, **~34 days on 1,024 H100s at the assumed 40% MFU**. 8TB generation is **$1M–$6M** by the assumed API path or **$70k–$280k** under the assumed self-hosted throughput. The dense compute-plus-data program is **~$4.1M–$11.2M**; **$10M–$50M** is a fully loaded planning allowance requiring vendor and staffing validation. We do not fund that until a 0.3B–3B world-model prototype beats the strongest cutoff-eligible baseline on a sealed real evaluation, and G0–G5 have passed. Pretrained systems with unknown or overlapping corpus cutoffs are reported separately.

**Ask:** fund the audit, the point-in-time benchmark, and the small prototype (Phases 0–2).

### Pitch for mid-range people

The kind of thesis EvanAI is designed to test is a chain: if a new computing method changes hardware demand, which suppliers become bottlenecks, when does the effect appear, and is it already priced?

EvanAI keeps the current state of those chains and asks what breaks if one node fails, then recommends long, short, or option, with horizon and size — or no trade.

We already built trading tests, including ones that throw out “wins” once real spreads show up. We will not throw those tests out. We also will not claim they already print money. First we prove the model only uses information that existed at the time. Then we prove it on real history it was not tuned against. Fake markets are practice. Real tape is the exam.

We are not raising for a 100-billion-parameter training run tonight. That is a later, expensive step if the small version works. One clean 100B run is millions of dollars and about a month on a thousand-GPU cluster after the data exists. One clean small-model run is hundreds to thousands of dollars in assumed GPU time; the complete proof also includes data, engineering, and evaluation. The path to a 30-billion-parameter gate is hundreds of thousands, not tens of millions.

**Ask:** 2–4 weeks for the initial audit, followed by roughly 2–6 months to build the point-in-time benchmark and complete the small-model comparison.

### Pitch for non-technical people

Some events look obvious after the fact and may have been visible as a chain at the time: this company depends on that supplier; if the supplier breaks, potential winners and losers can be mapped. Most people do not hold that complete picture. We want software that does, then decides how to trade it — or decides not to.

We are not asking you to believe a giant new AI trained from scratch. We already have tools that grade trades more realistically, including when a “win” disappears once real trading costs show up. Made-up markets are for practice; grading happens on real data the model did not see during training. Next step is to make sure the old model did not use future information, then test a smaller version of the new idea.

If that works, we scale. If it does not, we have not spent a fortune to find out.

**Ask:** back the first proof, not the finished super-model.

---

## 13. Meeting script

**Open (15 seconds).** We are not building a model that guesses tomorrow’s price. We are building a model of how the market’s moving parts connect, then a trade on top of that.

**Status.** We already have a backtest and options harness. We do not know if the last model had an edge. We freeze it and check whether it saw the future.

**Trap.** Training on stories we wrote, then celebrating a high score. Practice, not performance.

**Ask.** Not a 100B training check. Time and backing for a leakage audit and a small world-model test on real history with a time cutoff.

**If asked how much for the big model.** One clean 100B pretrain is millions of dollars and weeks on a large GPU cluster *after* the data exists. The whole program costs more. We should not write that check until the small test works. One clean small-model run costs hundreds to thousands of dollars in assumed GPU time; the complete proof costs more.

**Do not say.** U1–U10.

---

## 14. Sources and assumptions

**Retrieved evidence packet** (not files in this repo):

- `wiki/agentic-trading-system.md:85-91` — options-harness EOD vs minute winner change, liquidity gates, and the closed 300-winner gate.
- `wiki/agentic-trading-system.md:75-79` — preregistered forward promotion and fail-closed evaluation.
- `wiki/model-fusion.md:23-47` — one provider sampled many times is not an ensemble.

**Model-knowledge / assumed, not measured here:** H100 peak and MFU, `6ND` training FLOPs, 16 bytes/parameter training memory, bytes/token, dense-model tokens/parameter heuristic, GPU-hour prices, API token prices, generation throughput, STaR and continuous-thought analogues, 200GB bf16 weight footprint, raw storage cost, and the $10M–$50M fully loaded planning allowance.

**Decision constraints.**

1. Synthetic evaluation cannot promote the model without transfer to sealed or prospective real data.
2. World model, trade policy, portfolio allocator, and risk engine stay separate.
3. Old checkpoint is quarantined and audited, not automatically discarded.
4. 2021 and 2025 named examples are demonstrations, not concealed tests.
5. 0.3B–3B proof and 7B–30B scaling study precede any 100B authorization.
6. Immediate funding target is the point-in-time benchmark and small-model proof, not a 100B run.
7. Do not soften simulator limitations L1–L5 or the E4 stop rule in any pitch.
8. Do not invent a single compute figure. Use the ranges in §10. Dense versus MoE must stay distinct.

---

*End of memo.*
