# Drystone evaluation protocol (new trials, 20–21 Oct 2026)

Status: **LOCKED on 18 Oct 2026**, before any evaluation data was taken, by the commit that changed this line
(`git log -- docs/EVAL_PROTOCOL.md`; the hash is also in `docs/STATUS.md`). Trial list `config/eval_plan.json`,
sha256 `e69deb9dc325212b3ccd455f3266a83af389b7951fd8d6a412bbb8b27993e114`. Nothing in this protocol, the settings, the trial list or the criteria changes from here on.

Correction (18 Oct, after lock 8a953e4): title date 21–22 Oct → 20–21 Oct. Administrative only; trial list, sha256, settings and criteria unchanged.
Correction (18 Oct, after lock 8a953e4): session 1 (T01–T12) moved forward to 18 Oct afternoon, in bright daylight; session 2 (T13–T25) stays as planned. Administrative only; trial list, sha256, settings and criteria unchanged.

## 1. Purpose
Test 2 (17 Oct) scored 82% accuracy, Brier 0.145 and 0 falls in the GREEN zone, but the uncertainty settings were
tuned on the same 11 trials, with an older perception pipeline. This evaluation checks the predictions on **new
trials** with the final pipeline, settings that are **locked before any data is taken**, and success criteria that
are written down first.

## 2. Locked settings and software
- Uncertainty: box position 1 cm, load centre 2 cm (standard deviations); friction 0.5; simulation seed 0.
- Zones: P(fall) < 10% GREEN, 10–50% YELLOW, > 50% RED; Monte Carlo 150 runs, up to 600 near a zone line, safer
  zone if still unsure.
- Suggestion rule A: green there and 1 cm further out (suggestions are not used in this evaluation).
- Perception: ArUco detector with the default threshold (adaptiveThreshConstant 7), 10 frames, stack by contact,
  facing direction from stacked markers only.
- Box catalogue `config/boxes.json`: boxes ID 0–2, 29 × 17 cm, heights 19.6 / 19.5 / 19.4 cm, 1.0 kg.
- Camera: laptop webcam, 1280×720, calibration `data/camera_laptop.yaml` (RMS 0.37 px).
- Decisions on AWS Lambda (`agent.py --aws`), image `drystone-service:3b023a4`. If AWS fails, the laptop computes
  the decision with the same code; that is logged and reported as a fallback.
- Code: the commit that locks this protocol. Trial list: `config/eval_plan.json`, made by
  `tools/make_eval_plan.py` (seed 20261021), sha256 `e69deb9dc325212b3ccd455f3266a83af389b7951fd8d6a412bbb8b27993e114`.

## 3. Trials
25 trials fixed in advance, in a shuffled order: 10 with 2 boxes (ID 0 + ID 1), 15 with 3 boxes (ID 0 + ID 1 at a
set shift + ID 2); 15 positive and 10 negative shifts. The expected zone and P(fall) below come from the locked
settings on ideal positions; the scored prediction is the one the agent makes from the camera during the trial.
Expected: 8 GREEN, 9 YELLOW, 8 RED. 11 trials sit close to a zone line on purpose: GREEN at 5–8%,
YELLOW at 10–14% or 39–43%, RED at 58–62% (T02, T06, T12, T13, T15, T16, T18, T20, T21, T23, T25). The expected P values add up to 8.6 falls in total.

Shift = how far the box sits to the right of the box directly below it (negative = left).

| Trial | Stack to build first | Box | Shift | Expected zone | Expected P(fall) |
|---|---|---|---|---|---|
| T01 | ID 0 | ID 1 | +14 cm | YELLOW | 35% |
| T02 | ID 0 | ID 1 | +11 cm | GREEN | 6% |
| T03 | ID 0 + ID 1 at +5 cm | ID 2 | +18 cm | RED | 93% |
| T04 | ID 0 | ID 1 | -13 cm | YELLOW | 29% |
| T05 | ID 0 | ID 1 | -16 cm | RED | 78% |
| T06 | ID 0 + ID 1 at -5 cm | ID 2 | -10 cm | GREEN | 5% |
| T07 | ID 0 + ID 1 at +0 cm | ID 2 | +13 cm | YELLOW | 27% |
| T08 | ID 0 | ID 1 | -10 cm | GREEN | 3% |
| T09 | ID 0 + ID 1 at +5 cm | ID 2 | +16 cm | RED | 73% |
| T10 | ID 0 | ID 1 | +18 cm | RED | 92% |
| T11 | ID 0 + ID 1 at +0 cm | ID 2 | +10 cm | GREEN | 1% |
| T12 | ID 0 + ID 1 at +5 cm | ID 2 | +11 cm | GREEN | 8% |
| T13 | ID 0 | ID 1 | +12 cm | YELLOW | 12% |
| T14 | ID 0 + ID 1 at +0 cm | ID 2 | -17 cm | RED | 88% |
| T15 | ID 0 | ID 1 | -14 cm | YELLOW | 39% |
| T16 | ID 0 + ID 1 at -5 cm | ID 2 | +12 cm | YELLOW | 14% |
| T17 | ID 0 + ID 1 at +0 cm | ID 2 | -12 cm | YELLOW | 17% |
| T18 | ID 0 | ID 1 | +15 cm | RED | 62% |
| T19 | ID 0 + ID 1 at +0 cm | ID 2 | +8 cm | GREEN | 0% |
| T20 | ID 0 + ID 1 at +0 cm | ID 2 | +15 cm | RED | 58% |
| T21 | ID 0 + ID 1 at -5 cm | ID 2 | -15 cm | RED | 61% |
| T22 | ID 0 | ID 1 | +6 cm | GREEN | 0% |
| T23 | ID 0 + ID 1 at -5 cm | ID 2 | -11 cm | YELLOW | 10% |
| T24 | ID 0 + ID 1 at +5 cm | ID 2 | -6 cm | GREEN | 1% |
| T25 | ID 0 + ID 1 at +5 cm | ID 2 | +14 cm | YELLOW | 43% |

## 4. Procedure
Setup, once per session:
1. Plain background and **bright light**: marker detection fails on faded markers in dim light (18 Oct).
   Camera about 1 m away.
2. **Clear both sides of the stack**: boxes fall to the right for positive shifts and to the **left** for negative
   shifts (10 of the 25 trials). Keep at least one box length (30 cm) free on each side.
3. **Laptop in front** of the stack, never to the left or right where a box can fall. Only the boxes of the trial
   are in view.
4. Run the agent in evaluation mode (Windows cmd, from the repository folder):
   ```
   .venv\Scripts\activate
   ```
   ```
   set DRYSTONE_URL=<Function URL>
   ```
   ```
   python tools/agent.py --calib data/camera_laptop.yaml --marker-mm 80 --aws %DRYSTONE_URL% --supervisor Yasin --eval-plan config/eval_plan.json --eval-start 1
   ```
   To continue in a later session, start at the next trial number (e.g. `--eval-start 13`).

Per trial (the agent shows the trial on screen and in the log as `trial_id`):
1. **Build the stack** shown on screen. For 3-box trials the agent draws where ID 1 goes (setup, not scored) and
   refuses to decide while ID 1 is more than 1.5 cm from its planned shift. The A/D keys are off; the shift comes
   from the trial list.
2. **SPACE: decision.** The agent reads the stack and decides at the planned shift. GREEN: place the box. YELLOW or
   RED: the box is placed anyway as a logged override (supervisor name, reason "evaluation").
3. **Place the box** in the wireframe, let go, **wait 5 seconds**, then **SPACE: check**. Do not touch the boxes
   during the wait.
4. **Outcome.** The check gives OK, OFF_PLAN or FELL. The agent then asks to confirm: Enter / y = the check is
   right, n = the opposite. If the box is not visible at all, the agent asks f (fell out of view) / p (not placed
   yet, look again).
5. Take the boxes off, out of view, and build the next trial's stack.

## 5. Outcome definition
- **Fell** = within 5 seconds after letting go, any box ends on the floor, drops, or tips over (the check says
  FELL, or the worker corrects the check). A box that tilts but stays on the stack **stood**.
- The worker confirms every outcome; a correction is logged (`corrected`) and reported.
- **Prediction** = P(fall) of the agent's decision for that trial (from the camera reading of the real stack), not
  the expected P in the table.

## 6. Metrics (`tools/eval_report.py`)
- Accuracy on clear trials (P < 10% or P > 70% at trial time): P ≥ 50% predicts a fall; share that matches.
- Falls: the observed number of falls against the predicted number Σp (P at trial time) and its 90% interval
  Σp ± 1.645·√Σp(1−p).
- Overall accuracy (P ≥ 50% predicts a fall, all trials): reported to compare with Test 2 (82%), **not a
  criterion** (see 7).
- Brier score: mean of (P − outcome)², outcome 1 = fell.
- Falls in the GREEN zone (count), and the fall rate per zone.
- Calibration table: P ranges 0–10, 10–30, 30–50, 50–70, 70–90, 90–100%: trials, mean predicted P, observed fall
  rate.
- Placement error: |deviation| from the check for boxes that stood (mean, median, max, share within 1 cm).
- Decision time on AWS Lambda (round trip), laptop fallbacks, retakes, f/p questions, outcomes corrected by the
  worker, trials that were refused because the setup was wrong.

## 7. Pass criteria (fixed now)
P below is the agent's P(fall) at trial time. The last column is the chance that a **perfectly calibrated** model
passes the criterion on this trial list: outcomes drawn with the planned P from section 3 (exact
Poisson-binomial; the joint figure from 200,000 simulated runs). It shows each criterion is fair, and that luck
plays a part with 25 trials.

| # | Criterion | Target | Chance a calibrated model passes |
|---|---|---|---|
| C1 | Falls in the GREEN zone | **0** | **78%**. With the GREEN P in this list (6, 5, 3, 1, 8, 0, 0, 1%), a calibrated model still sees ≥ 1 GREEN fall about **22%** of the time. Kept at 0 because a fall in GREEN is the failure that matters most for safety. |
| C2a | Accuracy on clear trials (P < 10% or P > 70%) | **≥ 85%** | **92%** (14 clear trials in the plan, expected accuracy 92%, at least 12 of 14 needed) |
| C2b | Total falls inside the 90% interval of the predicted number, Σp ± 1.645·√Σp(1−p) | inside | **91%** (planned: Σp = 8.6, interval **6–11 falls**; the report recomputes it from P at trial time) |
| C3 | Brier score | **≤ 0.20** (0.25 = always saying 50%) | **97%** (expected Brier of a calibrated model on this list: **0.125**) |
| C4 | Trials with an outcome | **≥ 20 of 25** | operational, not a model property |

The evaluation passes only if all criteria pass. A calibrated model passes C1, C2a, C2b and C3 together about
**70%** of the time; a FAIL is reported as a FAIL, with the criterion that failed.

Why not "overall accuracy ≥ 80%" (the Test 2 target): this list is full of trials close to a zone line on purpose,
where even a perfect model is often "wrong" on a single trial. On the planned P, a perfect model is expected to
score about 82% overall accuracy and would fail an 80% target about 27% of the time. Overall accuracy is still
reported, next to Test 2 (82%), but it is not a criterion.

## 8. Rules that keep it honest
- Settings, thresholds, the catalogue, the trial list and the criteria do not change after the first trial.
- A trial is never removed because of its outcome. A trial may be **re-run only before its check**, if the setup
  was wrong (wrong box, camera moved, a hand in view); the log keeps every run, and the report uses the last
  completed one and lists the re-runs.
- If a software bug stops the evaluation, fix only the bug (no setting), note it in the report, and continue at
  the next trial.
- All trials are reported, including the ones that make Drystone look bad.

## 9. Failure cases for the report
Always written up: every fall in the GREEN zone, every wrong prediction (P ≥ 50% and stood, or P < 50% and fell),
every outcome the worker corrected. If there are fewer than three of those, add the trials with the largest
|P − outcome|. Also list the operational incidents (laptop fallback, retake, f/p question, setup refused).
For each case: trial ID, stack and shift, P(fall) and zone, what happened, the decision and check photos (faces
cropped or blurred), the most likely cause, and what we would change. The locked settings are not changed in this
evaluation.

## 10. Data
The logs (`data/agent_*/log.jsonl`) and photos stay on the laptop; they show people and rooms. The report
(`data/eval_report/trials.csv`, `summary.md`) has no photos and no names and goes into the repository.
