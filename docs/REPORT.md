# Drystone: technical report

*Predict before you stack.* OpenCV AI Competition 2026. Draft of 18 Oct 2026, with the results of the evaluation
on new trials (section 6.4). Every number in this report comes from `docs/STATUS.md` or from the agent logs it cites.

> Drystone is a **decision-support prototype, not a certified safety device**. It estimates a risk; a person makes
> every decision and places every box.

## 1. Problem
Stacking boxes by hand is a judgement call: how far can the next box hang over the one below before the stack
falls? People guess. A wrong guess drops a box on the floor, or on someone's foot. The physics is well known, but
in practice nobody measures the positions, the overhang or the load before placing the next box.

Drystone measures and predicts *before* the box is placed. One calibrated camera reads where each box is, a
physics simulation estimates the chance that the stack falls with the next box at the planned spot, and an agent
turns that number into an action and checks the result afterwards.

## 2. Users
- **The worker** who stacks the boxes: sees on screen where the next box can go, and is told when it should not.
- **The supervisor** who is accountable for risky placements: approves borderline ones, and can override a
  rejection only with a name and a reason, which is logged.
- **Whoever reviews incidents later**: every decision, approval, override and check is in a log with the photo.

## 3. Architecture

```mermaid
flowchart LR
    cam["Webcam 1280x720<br/>(ChArUco calibration)"] --> cv["OpenCV 5<br/>ArUco detection + pose<br/>10 frames, median"]
    cv --> twin["Digital twin<br/>stack by contact, box catalogue"]
    twin --> sim["MuJoCo Monte Carlo<br/>150-600 simulations"]
    sim --> agent["Agent rules<br/>GREEN / YELLOW / RED<br/>suggestion with 1 cm margin"]
    agent --> human["Supervisor<br/>approve / suggestion / override + reason"]
    human --> place["Box placed"]
    place --> check["Check again<br/>OK / OFF_PLAN / FELL"]
    check --> cv
    agent -. "--aws" .-> lambda["AWS Lambda + Function URL<br/>same code, CloudWatch Logs"]
```

| Part | Where | What it does |
|---|---|---|
| Perception | `tools/agent.py` (`read_scene`, `build_stack`) | markers → box poses → the stack, by contact |
| Decision core | `tools/drystone_core.py` | static check, Monte Carlo P(fall), zones, suggestion search, check after placement |
| Live agent | `tools/agent.py` | camera loop, wireframes, human control, JSONL log with photos |
| Service | `tools/service.py` | AWS Lambda handler: photo API for the agent, judges' web page and its API |
| Web page | `web/index.html` | sample photos, slider, decision, numbered trace, use suggestion, override |

All decision rules live in one file, `drystone_core.py`. The laptop agent and the Lambda service call the same
code; no rule is written twice, and no language model decides anything.

## 4. OpenCV 5 implementation
- **Calibration.** ChArUco board 7×5 (30 mm squares, DICT_5X5_100) glued to a flat board; automatic capture
  rejects duplicate views. The laptop webcam: **61 views, RMS reprojection error 0.37 px, focal length 900.0 ± 3.9
  px (0.43%), 12/12 image regions covered** (`data/camera_laptop.yaml`). A calibration is used only if it passes
  a quality check (RMS ≤ 1 px, focal uncertainty ≤ 1%, ≥ 9/12 regions, ≥ 10 views). A first attempt with a hand-held
  paper board gave 1.18 px and a focal length off by ±75 px; it was rejected.
- **Markers and pose.** An 80 mm ArUco marker (DICT_4X4_50) in the middle of each box's front face, detected with
  sub-pixel corner refinement; pose with `solvePnPGeneric` (IPPE square), and the ambiguous flat-marker solution
  resolved toward the base box orientation.
- **Steady positions.** One marker's facing direction wobbles by a few degrees from frame to frame; pushing the
  marker centre back along that direction made box positions jump by **1.5–3.6 cm**. Drystone averages the facing
  direction of all stacked markers over 10 frames (chordal mean of rotations) and takes the median position of each
  box: the jitter fell to **±0.1 cm** in a synthetic test. Test 1 (one marker): random error RMS **0.18 cm** (max
  0.47 cm), rotation ≤ 2.2°.
- **The stack by contact.** The stack is built from the bottom box up: the next box must rest on the top of the
  one below (within 4 cm) and overlap it. Other visible boxes are "off the stack" (floor, beside, or in the air).
  The facing direction comes from the stacked markers only: before this, one box that fell and lay turned 50° on
  the floor tilted the whole stack frame by **16°**.
- **Rejected change.** A lower adaptive threshold (`adaptiveThreshConstant` 7 → 3) read one faded marker that the
  default missed (148 real photos: 341 vs 340 markers, 0 false detections), but moved marker corners by up to
  **6.4 px** onto the white paper in darker photos and box positions by up to **61 mm** in 44 readings. It was
  rejected; missed markers are handled by asking the worker instead (section 7.4).

## 5. AWS deployment
- **AWS Lambda, container image** (OpenCV 5 + MuJoCo + NumPy are too large for a zip), x86_64, 2048 MB, 60 s
  timeout, region ap-southeast-1, image in Amazon ECR. One **Function URL** serves:
  the photo API for `agent.py --aws` (decide / check), the judges' page and sample photos, decisions for the
  samples, and the supervisor log (one JSON line per choice in **CloudWatch Logs**, without the IP address).
- **Same code on both sides.** If AWS fails, the laptop computes the decision with the same code and logs that it
  did.
- **Deploys** are tagged with the git commit hash; the live version and the rollback target are written in
  `docs/STATUS.md` before each deploy. Live now: `drystone-service:3b023a4`.
- **Speed.** Stopping each simulation as soon as a box falls or every box is at rest gave identical results on
  1,500 samples and about 2.9× less time; a YELLOW case on Lambda went from 16.3 s to 3.8–5.6 s. In the 18 Oct
  practice: RED decisions **8.5–10.4 s** round trip from the laptop (China → Singapore), checks **2.9–6.9 s**.
- **Public endpoint protection.** Web JSON ≤ 16 KB, photo POST ≤ 2 MB, 60 GET and 20 POST per minute per IP and
  container, decisions for the samples cached (at most 99 per container). Reserved concurrency cannot be set (account
  limit 10). The account is a paid account: costs above the always-free quota are billed, with a zero-spend budget
  alarm; the worst case (10 busy executions × 2 GB) is about USD 1.20 an hour.

## 6. Evaluation
### 6.1 Perception
Calibration and Test 1: section 4.

### 6.2 Test 2: prediction vs reality (17 Oct)
12 trials with 2–3 real boxes and 20–65% overhang, 11 counted.

| Uncertainty settings | Correct | Brier | Falls in GREEN |
|---|---|---|---|
| position 0.5 cm, load 1 cm (first) | 9/11 (82%) | 0.177 | **1** |
| position 1 cm, load 2 cm (current, recomputed on the same trials) | 9/11 (82%) | 0.145 | **0** |

Both wrong predictions were on the dangerous side and close to the edge (centre-of-mass margins 1.3 and 2.5 cm),
which is why the uncertainty was raised. The current settings were tuned on these same trials, so they had to be
confirmed on new trials (6.4). Test 2 also used the older perception (section 4).

With the measured box heights (19.4–19.6 cm instead of 19 cm) Test 2 and the sample zones are unchanged; a
control test showed height barely moves P(fall) (19 → 40 cm: 26.7% → 28.0% at +13 cm). What decides is where the
centre of mass sits relative to the edge below.

### 6.3 Practice with real boxes (18 Oct, `agent.py --aws`)
- 7 RED placements forced by override (P(fall) 86–98%): **7/7 fell, 7/7 detected as FELL**.
- Real placements landed **0.0–1.3 cm** from the plan. A suggestion right at the 10% line (+9 cm, P 5%) placed
  1.3 cm out turned the stack YELLOW 18%; this led to the 1 cm margin rule (section 7.2).
- Final scene: GREEN → RED 93% → override → fell → FELL → re-planned → suggestion +9 cm → OK (−0.3 cm), stack
  GREEN 1%.

### 6.4 Evaluation on new trials (18 Oct): FAIL on C2b by one fall
Protocol `docs/EVAL_PROTOCOL.md`, locked before any data (commit `8a953e4`): 25 pre-set trials in a shuffled order,
settings frozen, outcome confirmed by the worker. All 25 trials ran in one session (18 Oct, 15:26–15:53, 26 minutes,
`agent.py --aws`); the protocol records this and two other administrative corrections (title date, session date).
Trial list, settings, criteria and code did not change after the lock (sha256 of the trial list unchanged, no diff
in `tools/`, `tests/`, `config/`). Per-trial data: `data/eval_report/trials.csv`; summary: `data/eval_report/summary.md`.

| Criterion (locked) | Result | Target | |
|---|---|---|---|
| C1 falls in the GREEN zone | **0 of 8** GREEN trials | 0 | PASS |
| C2a accuracy on clear trials (P < 10% or > 70%) | **14/14 (100%)** | ≥ 85% | PASS |
| C2b total falls inside the 90% interval of the predicted number | **12 falls**; Σp = 8.537, sd 1.772, interval 5.62–11.45 → 6–11 | inside | **FAIL** |
| C3 Brier score | **0.125** | ≤ 0.20 | PASS |
| C4 trials with an outcome | **25 of 25** | ≥ 20 | PASS |

**Verdict: FAIL** under the locked criteria, because of C2b: one fall more than the upper end of the interval
(z = 1.96). A calibrated model with these P would see 12 or more falls only 4.7% of the time, so this is a real
signal, not bad luck: **the model under-predicts falls.** Overall accuracy (P ≥ 50% predicts a fall), which is not a
criterion, was **84% (21/25)**, against 82% in Test 2.

| Zone | Trials | Falls | Fall rate | Mean P(fall) |
|---|---|---|---|---|
| GREEN | 8 | 0 | 0% | 3% |
| YELLOW | 9 | 4 | 44% | 25% |
| RED | 8 | 8 | 100% | 75% |

| P(fall) range | Trials | Mean predicted | Observed fall rate |
|---|---|---|---|
| 0–10% | 9 | 4% | 0% |
| 10–30% | 5 | 20% | 40% |
| 30–50% | 3 | 39% | 67% |
| 50–70% | 3 | 60% | 100% |
| 70–90% | 3 | 80% | 100% |
| 90–100% | 2 | 92% | 100% |

Operations: placement error of the boxes that stood: mean 0.6 cm, median 0.6 cm, max 1.7 cm (10/13 within 1 cm;
T06 was 1.7 cm off and stood). Decisions on AWS Lambda: median 7.6 s, max 11.1 s round trip, 25/25 on AWS. Retakes
0, f/p questions 0, laptop fallbacks 0, outcomes corrected by the worker 0. The agent refused to decide 4 times
because the setup was wrong (T03: ID 1 at +10 cm instead of +5 cm, twice; T09: ID 1 not placed yet, twice).

#### Failure cases
The protocol requires every GREEN fall (none), every wrong prediction and every corrected outcome (none). The four
wrong predictions are all **YELLOW trials that fell**:

| Trial | Stack | Shift | Centre-of-mass margin | P(fall) | Outcome |
|---|---|---|---|---|---|
| T16 | 3 boxes, ID 1 at −4.6 cm | +12 cm | +2.5 cm | 14% | fell |
| T17 | 3 boxes, ID 1 at −0.2 cm | −12 cm | +2.5 cm | 17% | fell |
| T01 | 2 boxes | +14 cm | +0.5 cm | 35% | fell |
| T25 | 3 boxes, ID 1 at +5.2 cm | +14 cm | +0.5 cm | 43% | fell |

The RED trials closest to the line (T18 62%, T20 58%, T21 60%; margin −0.5 cm) all fell too: correct, but they also
show the model is too cautious about the stack *standing* near the edge.

Ordered by the static centre-of-mass margin, the picture is clear: every trial with a margin of −0.5 cm or less fell
(8/8, all predicted RED), every trial with +3.5 cm or more stood (9/9, all GREEN or 9%), and in between, from +0.5
to +2.5 cm, **4 of 8 fell** while the model predicted 12–43%. The model ranks the risk correctly and keeps GREEN
safe, but it is **too optimistic in the middle band**. In that band 3 of the 4 three-box trials fell (T16, T17, T25;
T07 stood) against 1 of 4 two-box trials (T01; T04, T13, T15 stood); with 8 trials this is a hint, not a finding.

Possible causes (hypotheses, not conclusions):
- **Friction** in the simulation (0.5) may not match these boxes and this floor (the post-hoc check below does not
  support "too high").
- **Load and centre of mass**: the 2 cm uncertainty of the load centre may be too small (contents shift; the box
  flaps add weight near the top).
- **The floor**: smooth tiles; the base box can slide or rock, which the simulation treats as fixed ground with the
  same friction.
- **How the box is released**: a small push or tilt when letting go matters most near the edge, and more for a box
  released 40 cm up (three-box trials) than 20 cm up.
- **Box compliance**: cardboard edges bend under an overhanging box; the simulation uses rigid boxes.

#### Post-hoc analysis (not used by the system)
**Post-hoc, not used by the system, nothing deployed.** P(fall) recomputed on the 25 stacks recorded in the log with
other simulation settings (the locked settings reproduce the logged P exactly, max difference 0.000):

| Position sd | Load-centre sd | Friction | Brier | Log-likelihood | Σp (90% interval) |
|---|---|---|---|---|---|
| **1 cm** | **2 cm** | **0.5 (locked)** | 0.125 | −9.61 | 8.54 (5.6–11.5) |
| 1 cm | 3 cm | 0.5 | 0.126 | −9.96 | 9.23 (5.9–12.6) |
| 1 cm | 4 cm | 0.5 | 0.132 | −10.69 | 10.42 (6.8–14.1) |
| 1.5 cm | 2 cm | 0.5 | 0.124 | −9.64 | 8.79 (5.7–11.9) |
| 2 cm | 2 cm | 0.5 | 0.121 | −9.63 | 9.24 (6.0–12.5) |
| 1 cm | 2 cm | 0.3 | 0.126 | −9.65 | 8.48 (5.6–11.4) |
| 1 cm | 2 cm | 0.8 | 0.123 | −9.43 | 8.74 (5.8–11.7) |
| 1.5 cm | 3 cm | 0.5 | 0.123 | −9.87 | 9.56 (6.1–13.0) |
| 2 cm | 3 cm | 0.5 | 0.124 | −10.14 | 10.10 (6.6–13.6) |

- No single global setting fixes the middle band: the Brier score stays between 0.121 and 0.132. More uncertainty
  raises Σp enough to bring 12 falls inside the interval, but it raises P everywhere, and the log-likelihood gets
  worse. Every setting still gives 0 falls in the GREEN zone.
- The "friction too high" hypothesis is **not supported**: a lower friction (0.3) gives *fewer* predicted falls.
- So the gap looks structural (how a box is released, cardboard compliance, the three-box case) rather than a
  wrong parameter. With 25 trials, tuning on this data would overfit it, exactly what this evaluation was designed
  to avoid.

Follow-up work (not done): a dedicated set of trials in the +0.5 to +2.5 cm margin band, split by two and three
boxes; measure box-on-box and box-on-floor friction with a tilt test; model the release (small random push or
tilt when the box is let go); then lock new settings and test them on new trials again.

## 7. Agentic Vision: perception → decision → action
### 7.1 The loop
1. **Perceive.** 10 frames → marker poses → digital twin of the stack, by contact. A bad reading (shaky, turned
   box, idle box in view) is retaken automatically or explained to the worker.
2. **Decide.** Monte Carlo P(fall) for the next box at the requested shift → zone → action. Not green → search the
   nearest safe spot with a 1 cm margin.
3. **Act with a human.** GREEN: guide (wireframe). YELLOW: the supervisor approves, uses the suggestion or rejects.
   RED: rejected; going on needs a suggestion or an override with a name and a reason.
4. **Perceive again.** After the box is placed: OK, OFF_PLAN (more than 1.5 cm off; the risk is computed again and
   the agent warns if the stack is no longer green) or FELL.
5. **Re-plan.** A box that fell is "not placed" again: the agent asks for it to be picked up and plans it again,
   with the same requested shift so the same risk and suggestion are shown. A box taken off the stack is noticed
   ("stack changed: ID 1 is missing") and planned again in order.

### 7.2 A real trace (final practice, 18 Oct, decision on Lambda)
```
computed on AWS Lambda (10.0 s round trip, 7.1 s on the server)
digital twin: 2 box(es) + candidate ID 2 overhanging +62% (+18.0 cm)
static check: falls (centre-of-mass margin -3.5 cm)
150 simulations: P(fall) = 93% +- 4%
not green -> searching the nearest safe position
try +12 cm (+41%): P = 15%
try +11 cm (+38%): P = 12%
try +10 cm (+34%): P = 4%, but 1 cm further out (+11 cm P = 12%) is not green -> no margin, keep looking
try +9 cm (+31%): P = 1%; 1 cm further out (+10 cm P = 4%) also green -> suggestion
```
Then: override → the box fell → check: "box ID 2 is on the floor next to the stack -> it fell" → "box ID 2 fell.
Pick it up and keep it out of the camera view, then press SPACE to plan ID 2 again." → RED again → suggestion
+9 cm → check OK (−0.3 cm), stack GREEN 1%.

**Suggestion margin.** On 7 cases (6 judges' examples + the practice stack) the margin moved suggestions 1 cm
closer: P at the suggestion 1–3%, and still ≤ 7% if the box lands 1 cm further out; without the margin, a 1 cm miss
gave P 10–14% (YELLOW).

### 7.3 Failure handling (each found in practice, fixed, and covered by a test)
| What happened | Fix |
|---|---|
| A box that fell next to the stack was read as part of the stack ("stack: [0, 2, 1]"), the message named the wrong box, and the check looped on retakes. | Stack by contact; the stack frame from stacked markers only; a planned box on the floor is FELL, without a retake. |
| After FELL the agent moved on, looped on retakes for the box still on the floor, and never offered it again. | The fallen box is "not placed" again; one instruction to pick it up; planned again with its suggestion. |
| A placed box whose marker was not read was counted as fallen ("not visible"). | If the box is nowhere in view and the stack below is intact, the agent asks: f = fell out of view, p = not placed yet (look again). |
| A box taken off the stack was skipped and the next ID was planned on the wrong stack. | "stack changed: ID 1 is missing" and planning in ID order. |
| Enter at a terminal question counted as an answer (Enter at f/p meant "fell"). | Empty answers are rejected unless explicitly allowed. |

The whole loop (GREEN → RED → override → fall → FELL → pick up → re-plan → suggestion → OK) runs in the test suite
with synthetic camera photos rendered through the real calibration, on the laptop and through the Lambda handler.

### 7.4 Observability
- Every event goes to `log.jsonl` with the photo: decisions (with the full trace), approvals, overrides (name,
  reason), suggestions used, checks, retakes and their reason, f/p answers, stack changes, fallbacks to the laptop,
  and the evaluation's `trial_id`.
- The judges' page shows a numbered trace with the time of each step (marker detection, digital twin, simulation,
  decision, action) and marks cached answers.
- Supervisor choices on the page are one JSON line in CloudWatch Logs.
- `tools/eval_report.py` turns logs into a per-trial table and metrics.

### 7.5 Human control
- The agent never moves a box; a person places every one.
- YELLOW needs a supervisor; RED can only go ahead by the agent's own suggestion or an override with a name and a
  reason. An override is logged and never changes the computed risk.
- When the camera cannot tell (box not visible), the agent asks instead of guessing.
- Safety rules are fixed, deterministic code: the same input always gives the same zone.

## 8. Limitations
- Markers are required on every box; faded markers in dim light can be missed.
- One calibration per camera and resolution; the service is calibrated for one webcam at 1280×720.
- Three measured boxes of one type (29 × 17 × 19.4–19.6 cm, 1.0 kg, load in the middle); other boxes, uneven or
  soft loads are untested.
- Test 1 showed an unexplained scale bias of about ±3%. The marker-to-marker height read 20.2 cm where the ruler
  gives 19.9 cm; the 0.3 cm left over is within that bias.
- Small samples: Test 2 has 11 counted trials; the practice runs are demonstrations; the evaluation has 25 trials.
- **The model under-predicts falls near the edge.** In the evaluation, trials with a centre-of-mass margin of
  +0.5 to +2.5 cm fell 4 times out of 8 while the model predicted 12–43%; the evaluation failed criterion C2b
  (12 falls against an interval of 6–11). Treat YELLOW as more dangerous than its number says.
- The public endpoint runs on a paid AWS account; rate limits and the cache are per container.

## 9. Responsible use
- Use Drystone to support a person's judgement, never as the only safeguard. It is not certified for safety.
- Keep people, hands and the laptop out of the direction a box can fall when testing risky placements.
- Overrides exist so that a person stays in charge; they are logged with a name and a reason so that decisions
  can be reviewed.
- Logs and photos show people and rooms; they stay on the laptop and are not published. Published data (CSV,
  reports) has no photos and no names.
