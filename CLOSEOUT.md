# Close-out plan

**Purpose.** Take this project to an honest finish, then stop. This file exists so that
"finish it properly" cannot quietly grow into "add every MLOps tool I have heard of".

**Hard stop.** ~20 hours of work, split into five phases. When Phase 4 is done, this repo
is archived and the next project starts. Nothing in the "Do not build" list gets built here.

**The rule that decides what belongs here.** In this project the *data* never moves, but the
*requests* do. Anything about the request path is real and worth building. Anything about the
data path is theatre. That single line explains every include and exclude below.

---

## What this project actually earned (measured, from audit/REPORT_*.md)

| what | number |
|---|---|
| Baseline, predict the mean | val MAE **1.0536**, r2 -0.0005 |
| LinearRegression | val r2 **0.7309**, MAE 0.5217 |
| DecisionTree(depth 6) | val r2 **0.7559**, MAE 0.4618 |
| RandomForest, defaults (shipped config) | val r2 **0.8624**, MAE **0.3441** |
| RandomForest, min_samples_leaf=5 | val r2 0.8295, MAE 0.3932 |
| RandomForest, min_samples_leaf=20 | val r2 0.7849, MAE 0.4592 |
| 5-fold CV on train | r2 **0.8555 +/- 0.0111**, MAE **0.3568 +/- 0.0114** |
| Cold start, spawn to /readyz 200 | **2598 ms** |
| Peak throughput, 1 uvicorn worker | **92.5 req/s** at concurrency 4, p95 **58.4 ms** |
| Errors across concurrency 1/4/16/64 | **0** |

**Honest headline:** MAE 0.3441 against a mean-baseline of 1.0536 — a **67.3% error
reduction**. Cross-validated r2 is **0.855 +/- 0.011**, not the 0.890 in metadata.json.

**The finding that matters most.** `gate.py` sets `MAX_TEST_MAE = 0.35` and
`MIN_TEST_R2 = 0.85`. Cross-validated MAE is **0.3568**, which is *above* the 0.35 limit. And
2 of the 5 CV folds (0.8452, 0.8402) fall *below* the 0.85 r2 limit. So this model **fails its
own quality gate** when measured over five splits instead of one. It passed because a single
70/30 split happened to be a lucky draw. That is the entire argument for Phase 1, and it is a
better interview story than any passing number.

---

## Phase 0 — make it runnable by a stranger (~3 h)

Nothing else counts until this is done. Right now no one but you can run this repo.

- [🗸] **0.1** Commit the 15 modified tracked files. Until this happens, the reviewed code
      exists in no commit and the hash in `metadata.json` identifies nothing.
- [🗸] **0.2** Create a GitHub repo and push. 46 commits currently live only on your laptop.
      A portfolio project with no URL is not a portfolio project.
- [ ] **0.3** Write `data/PROVENANCE.md`. Go find the GitHub repo you took the CSV from and
      record the URL, the date you downloaded it, and the sha256 already in `metadata.json`
      (`32b542a4…`). If you cannot find the source, write that down too — "origin
      undocumented" is a real finding, not an embarrassment.
- [ ] **0.4** Add `scripts/fetch_data.py` that downloads the CSV to `data/raw/` and checks the
      sha256, or — if licensing is unclear — document the manual step in the README. A cloner
      must have some path to a working `data/raw/`.
- [ ] **0.5** Make `save_artifact` raise instead of writing when `_git_dirty()` is True. The
      shipped artifact says `dirty: true`, which means your provenance record cannot reproduce
      your model. Fixing this is 3 lines and it repairs the one thing you built well.
- [ ] **0.6** Add a `Dockerfile` and a `Makefile` with `make train`, `make serve`, `make test`.
      This is *not* the ops theatre from the "do not build" list. A container answers "can a
      stranger run this", which is a reproducibility question, not a monitoring question.
      Roughly 45 minutes.
- [ ] **0.7** Check whether `.github/workflows/` actually contains a workflow file — the audit
      only saw the directory. Even if a workflow exists, **it has never run once**, because
      there was no remote for GitHub to run it on. After 0.2 it will run. Make it do
      `uv sync` + `pytest`. Your 6 test files are real regardless of whether the data moves.

**Done when:** you can clone into an empty folder, run three documented commands, and get a
trained artifact plus a serving API. Test this by actually cloning into a temp folder.

---

## Phase 1 — fix the measurement defects (~5 h)

- [ ] **1.1 Three-way split in `train.py`.** Currently one 70/30 split, metrics computed on
      the 30%, and those same metrics handed to `gate()`. The split you report is the split you
      select on, so 0.890 is a selection score, not a held-out score. Change to
      train 60 / validation 20 / test 20. Select and gate on validation. Touch test **once**,
      at the very end, and write that number to metadata as `test_final`.
- [ ] **1.2 Rewrite the gate on cross-validation, not one split.** Replace the current pass/fail
      with: 5-fold CV on train+validation, and require `cv_mae_mean + cv_mae_std < MAX_MAE`.
      Store the fold list in metadata. Right now your CV MAE of 0.3568 breaches your own 0.35
      limit — the honest options are to raise the limit and say why, or admit the model does not
      clear the bar you set. Pick one deliberately and write the reason in an ADR.
- [ ] **1.3 Delete the `abs(train_r2 - test_r2) < 0.15` check.** For a RandomForest grown to
      pure leaves, a high train score is how the algorithm works, not evidence of a problem.
      Proof from your own audit: regularising *hurt* — `min_samples_leaf=5` dropped val r2 from
      0.8624 to 0.8295, and `=20` dropped it to 0.7849. So the defaults are genuinely the best
      of the three, and the gap statistic was measuring nothing useful. It also passed by only
      0.0314 of margin (0.1186 vs 0.15), so it was one unlucky split away from blocking a good
      model for the wrong reason. Replace it with the CV spread from 1.2.
- [ ] **1.4 Fix the double catch-all on `Country`.** Confirmed: the literal string `'Other'`
      exists in the CSV **and** `OneHotEncoder(max_categories=11)` builds its own
      `Country_infrequent_sklearn` bucket, so two "everything else" columns compete and
      `metadata.json` lists both. Decide which one owns unseen values, and make it explicit.
- [ ] **1.5 Do not run a hyperparameter search.** Your audit already compared three
      configurations and the shipped one won. Record that in an ADR as "search performed,
      defaults retained, evidence attached" rather than adding a grid search that will find the
      same answer more slowly.

**Done when:** `metadata.json` carries `cv_r2_mean`, `cv_r2_std`, the fold list, and a
`test_final` block that was computed exactly once.

---

## Phase 2 — the README, which is the real deliverable (~4 h)

`README.md` is currently 0 bytes and untracked. It is the first and often only thing a reviewer
reads. Write these seven sections, in this order.

- [ ] **2.1 What this is, in three sentences,** including the word "educational" and the fact
      that it is not a clinical instrument.
- [ ] **2.2 The result, with the baseline first.** "Predicting the mean gives MAE 1.0536. This
      model gives MAE 0.3441 — a 67.3% reduction. Cross-validated r2 is 0.855 +/- 0.011."
      Never write 0.890 again without the word "lucky split" next to it.
- [ ] **2.3 The lucky-split story.** Say that the first reported figure was 0.890, that five-fold
      CV put the true value at 0.855 +/- 0.011, that 0.890 sat about three standard deviations
      above the mean, and that this is why the gate was moved onto cross-validation. This
      paragraph is worth more than every metric in the repo, because almost no student portfolio
      contains a self-caught measurement error.
- [ ] **2.4 What the model is actually using.** From permutation importance on held-out data:
      shuffling `Avg_Daily_Usage_Hours` costs **0.9273** r2 — it alone destroys the model.
      `Sleep_Hours_Per_Night` costs 0.2292. Everything else is 0.09 or less, and
      `Stress_Level` (0.0058) and `Academic_Level` (0.0057) contribute essentially nothing.
      State plainly: this is a two-variable model wearing twelve features.
- [ ] **2.5 The ablation table,** copied from the audit. Note honestly that the country encoding
      work in ADR 0001 **did earn its place** (-0.0247 r2 when dropped, third highest
      permutation importance at 0.0913), while `Stress_Level` did not (-0.0017).
- [ ] **2.6 A data-quality warning section.** The evidence that this dataset is generated rather
      than measured: only 7 distinct ages, exactly 2 genders, and whole-number target values
      over-represented against their neighbours by up to **3.35x** (6.0 appears 424 times while
      5.9 appears 134 and 6.1 appears 119). Add that the origin is an undocumented GitHub repo.
      Conclusion to write down: r2 0.855 may largely measure how well the model recovered
      somebody's data-generating formula. Also note the learning curve is still rising at 100%
      of the data (0.7890 → 0.8209 → 0.8466 → 0.8624), which on generated data means the
      formula has not been fully recovered yet — not that real-world accuracy would improve.
- [ ] **2.7 "What I deliberately did not build, and why."** Copy the list from the bottom of
      this file. This is the section that turns a small project into evidence of judgment.

**Done when:** a reader who never opens the code knows the honest accuracy, the two features
that matter, the dataset's problems, and what you chose to leave out.

---

## Phase 3 — five experiments on the request path (~5 h)

These are the production concepts that are **genuinely learnable here**, because they are about
requests arriving, not about data arriving. Each one must end with a number you measured or an
error you caused. Write the result in `docs/insights/`.

- [ ] **3.1 Prediction log (~45 min).** Add a SQLite table: `id`, `timestamp`, `input_json`,
      `output`, `model_version`, `latency_ms`. Write one row per `/predict` call. Then run the
      load test again and query what you captured.
      *Why this is real:* every other monitoring idea needs moving data. This one needs moving
      *requests*, which you have. It is also the thing that, if missing, makes it permanently
      impossible to measure a model after the fact — that door closes as time passes.
- [ ] **3.2 Worker scaling (~30 min).** Your API peaked at **92.5 req/s** on a machine with 16
      logical CPUs, and throughput went *down* past concurrency 4 while p95 climbed from 58.4 ms
      to 804.5 ms at concurrency 64. Re-run `audit/audit_serving.py` against uvicorn started
      with `--workers 4`, then `--workers 8`. Record the new peak.
      *What you should learn:* one Python process cannot use 16 cores, because only one thread
      runs Python code at a time. The fix is more processes, not more threads. At concurrency 64
      almost all of that 800 ms was time spent waiting in a queue, not time spent predicting —
      check it yourself: 64 in flight divided by 87.3 req/s predicts about 0.73 s of latency,
      and the measured mean was 0.709 s. When a queue is the bottleneck, latency grows in
      proportion to how many requests are waiting.
- [ ] **3.3 Break the schema on purpose (~45 min).** Three separate runs: add a column to the
      CSV, delete a column, and change `Age` from int to string. Record for each one *where* it
      failed (pandera at load, sklearn at transform, or silently at predict) and *how loud* the
      failure was.
      *What you should learn:* the difference between failing at the front door and failing
      quietly three layers in. The second kind is what causes real production incidents.
- [ ] **3.4 Shadow-run two models (~1 h).** Load both the shipped model and the
      `min_samples_leaf=5` model. Serve the shipped one's answer to the caller, but log both.
      Compare after 500 requests.
      *Why this is real:* shadow deployment means running a new model on real traffic without
      letting it affect anyone. It needs traffic, not moving data — so unlike canary
      deployment (which needs a slice of real users you do not have), you can genuinely do
      this today.
- [ ] **3.5 Make the 500 handler talk (~20 min).** The bare `except Exception` handler currently
      returns 500 with no log line. Add structured logging with a request id, the exception type,
      and a traceback. Then trigger a real 500 and confirm you can find it.
      *What you should learn:* an error your system does not record is an error you cannot fix.

**Done when:** five short notes exist in `docs/insights/`, each containing a number or an error
message you produced yourself.

---

## Phase 4 — one recording (~3 h)

- [ ] **4.1** Do a private run-through first and mark every point where you hesitate. Each
      hesitation is a gap in your own understanding, not a presentation problem.
- [ ] **4.2** Record one video with this spine: what the system does → the honest numbers with
      the baseline → the lucky-split mistake and how you caught it → the two features that carry
      the model → the saturation curve and the worker fix → what you deliberately did not build
      and why.
- [ ] **4.3** Publish only after Phases 0-3 are complete. Publishing before that broadcasts an
      unpushed repo, an empty README, and a metric you have since shown to be a lucky draw.

**Do not** make a series about a hypothetical production architecture for this project. Save
that format for the next project, where you will be describing a system you actually ran.

---

## Deliberately not built, and why

Copy this table into the README. Each row is a decision with a reason, which is the opposite of
an unfinished to-do list.

| not built | why it would be theatre here |
|---|---|
| Prometheus + Grafana dashboards | The only thing worth charting would be request metrics, and a single load test already produced those numbers. A dashboard nobody watches is a screenshot. |
| Drift monitoring | Drift means the incoming data has changed. This dataset is one fixed file, so any drift metric computed on it is a flat line by construction. |
| Scheduled retraining | Retraining on identical rows produces an identical model. The pipeline would run, succeed, and change nothing. |
| Feature store | A feature store solves computing the same feature the same way in training and serving, and looking up a feature's value *as it was* at some past moment. With no timestamps and no repeated entities, there is nothing to solve. |
| Canary / A-B testing | Both need real users to split. There are none. |
| Autoscaling, Kubernetes | Scaling responds to varying traffic. Traffic here is whatever the load script sends. |
| Queues / backpressure | These matter when arrivals exceed what you can process for a sustained period. Zero errors were recorded up to concurrency 64. |
| Streaming ingestion | Nothing arrives. |

---

## Where the "what if data moved" learning belongs

It is **mostly independent of this project**, and the split is clean:

- **Request-path concepts are real here** — prediction logging, structured logs, latency and
  saturation, process vs thread parallelism, cold start, shadow deployment, schema breakage.
  All five Phase 3 experiments live here. Do them here.
- **Data-path concepts cannot be learned here** — batch vs streaming, drift, retraining
  triggers, late labels, feature stores, point-in-time correctness. Study these anchored to the
  *next* project, so each answer becomes a design decision that later gets tested by reality
  rather than a hypothetical that never gets checked.

Practical consequence: do not delay this close-out to study data-path concepts, and do not study
data-path concepts by writing documents about this repo.

---

## Definition of done for the whole project

1. Pushed to GitHub with a non-empty README.
2. A stranger can clone it and reach a trained model plus a running API from documented commands.
3. Every number in the README is cross-validated or measured, and the baseline appears before
   the score.
4. `metadata.json` from a clean tree, so the recorded commit reproduces the model.
5. Five insight notes in `docs/insights/` containing measurements you took.
6. A "not built, and why" table.
7. One recording.

Then archive it and start the next project. Do not return to add tools.

---

## Do not do these, at any point

- Add a tool in order to learn a concept. Learn the concept from a 45-minute experiment, then
  decide whether the tool is warranted.
- Write "production-ready", "scalable", or "end-to-end MLOps" anywhere in the README. The load
  numbers are yours and defensible; the adjectives are not.
- Quote r2 0.890 as the result.
- Spend more than the stated hours. The reason is not that the work is bad — it is that roughly
  40% of what you want to learn cannot be built on a fixed CSV at any hour count, so hours 21
  onward buy less here than hour 1 buys on the next project.

