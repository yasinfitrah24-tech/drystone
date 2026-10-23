# Drystone: Devpost submission draft

Draft text for the Devpost form; Yasin fills the form. Every number comes from `docs/STATUS.md`, `docs/REPORT.md` or
`data/eval_report/`; statistics have the same sources as the report (section 11). The live demo link goes in the
Devpost "Try it out" field, not in this file.

**For Yasin, image gallery:** upload `docs/img/architecture.png` first, then `docs/img/agent_loop.png` (both
1920×1080 PNG, about 0.23 MB each; checked: no Function URL or account number in the pictures or their metadata).

## Tagline
Predict before you stack: a camera, OpenCV 5 and a physics simulation estimate the chance a stack of boxes falls
before the next box goes on.

## Inspiration
Stacking boxes by hand is a judgement call: how far can the next box hang over the one below before the stack
falls?

In US transportation and warehousing in 2020, the Bureau of Labor Statistics counted 99,800 nonfatal cases with
days away from work. Of these, 12,100 were "struck by object or equipment". There were also 65 fatal injuries from
"contact with objects and equipment" (62–75 a year in 2016–2020). The figures combine transportation with
warehousing, and the categories cover much more than falling stacks, so they show the scale of the problem and
**not** how many people are hurt by falling stacks of boxes.

US OSHA requires materials stored in tiers to be stacked, blocked, interlocked and limited in height so that they
are "stable and secure against sliding or collapse". In November 2025, Oregon OSHA reported a 39-year-old worker
killed when two stacks of lumber fell on him (initial penalties USD 43,401), and a retail case where boxes stacked
more than 7 feet high collapsed and trapped an employee at the waist.

Drystone is a low-cost decision aid for this: a webcam and printed markers that estimate the risk before the box is
placed.

## What it does
- A calibrated webcam reads an ArUco marker on every box, and OpenCV 5 turns the markers into a digital twin of the
  stack.
- For the next box at the planned spot, a MuJoCo Monte Carlo simulation (150–600 runs, with position and load
  uncertainty) estimates P(fall).
- An agent turns the risk into an action. GREEN (under 10%) guides the placement, YELLOW (10–50%) asks a supervisor,
  and RED (over 50%) rejects it and suggests the nearest spot that stays green even if the box lands 1 cm further
  out. Going on after a rejection needs an override with a name and a reason, which is logged.
- After the box is placed, the camera checks the result: OK, OFF_PLAN or FELL. A box that fell is planned again. If
  a box is not visible, the agent asks the supervisor.
- The same decision code runs on the laptop and on AWS Lambda. Judges can try it on a public web page with three
  real sample photos, a placement slider with a preview of the next box, the decision, a numbered trace with timings, "use suggestion" and
  "override".

Drystone is a decision-support prototype, **not a certified safety device**. We tested it only on three uniform
1.0 kg cardboard boxes, not on real warehouse loads such as lumber or full cartons stacked above head height.

## How we built it
- OpenCV 5: ChArUco calibration with a quality gate (61 views, reprojection error 0.37 px, focal length
  900.0 ± 3.9 px), ArUco DICT_4X4_50 markers with sub-pixel corners, `solvePnPGeneric` (IPPE square), the facing
  direction averaged over all stacked markers and 10 frames, and the stack built by physical contact from the bottom
  box up.
- Physics: MuJoCo. Each run stops as soon as a box falls or all boxes are at rest (identical results on 1,500
  samples, about 2.9× faster). Near a zone line the agent runs more simulations, and takes the safer zone when it is
  still unsure.
- Agent: deterministic rules in one file (`drystone_core.py`), shared by the laptop agent and the cloud. No language
  model makes a decision. Every decision, approval, override and check is logged with its photo.
- AWS: a container image in Amazon ECR runs on AWS Lambda (2048 MB) behind a Function URL. It serves the agent's
  photo API and the judges' page with its API, and supervisor choices go to CloudWatch Logs. Deploys are tagged with
  the git commit, and a lifecycle policy keeps the previous version for rollback. The service also has request
  limits, a cache and a zero-spend budget alarm.
- Testing: 66 automated tests. Many use synthetic camera photos rendered through the real calibration, including
  the whole agent loop with a fake camera, both on the laptop and through the Lambda handler.

## Challenges we ran into
- Our first calibration used a hand-held paper board that was slightly curved. It gave a 1.18 px error and a focal
  length off by about ±75 px. Gluing the board to a flat, hard board and adding a quality gate brought the error to
  0.37 px.
- One faded marker was missed in a darker photo. A lower detection threshold read it, but when we validated that
  change on 148 real photos, marker corners moved by up to 6.4 px onto the white paper and box positions by up to
  61 mm in 44 readings. We rejected the change. When a marker is missing, the agent now asks the supervisor whether
  the box fell out of view or is not placed yet.
- In practice with real boxes, a box that fell next to the stack was read as part of the stack, the message named
  the wrong box, and the agent looped on retakes. We rebuilt the stack reading around physical contact and took the
  stack's orientation from stacked markers only (a turned box on the floor had tilted it by 16°). A fallen box is
  now "not placed" again, to be picked up and planned again.
- A suggestion at P 5% landed 1.3 cm off in practice and turned the stack YELLOW (18%). Real placements landed
  0.0–1.3 cm from the plan, so a suggestion must now also be green 1 cm further out. Suggestions moved 1 cm closer,
  with P 1–3%.
- On our 25 evaluation trials, a simple static centre-of-mass check is exactly as accurate as the simulation (84%
  both). The simulation is better calibrated (Brier 0.125 against 0.160), and it gives a graded risk with its
  uncertainty, which the agent needs to choose between guiding, asking and rejecting.

## Accomplishments that we're proud of
- We ran a locked evaluation: 25 pre-set trials, shuffled, with settings and pass criteria locked in git before any
  data. **0 falls in the GREEN zone** (0 of 8), every RED trial fell (8 of 8), **14/14 correct on clear cases**,
  **Brier 0.125**, all 25 trials completed, overall accuracy 84% (82% in our earlier Test 2). One criterion
  **failed**: 12 boxes fell where the model predicted 8.5 (90% interval 6–11). The model is too optimistic close to
  the edge: trials with a centre-of-mass margin of +0.5 to +2.5 cm fell 4 times out of 8 against a predicted
  12–43%. We report it as a FAIL and did not tune on the evaluation data.
- The loop works with real boxes. In practice, 7 of 7 forced RED placements fell and all 7 were detected as FELL. In
  the evaluation, the check after placement agreed with the worker on 25 of 25 outcomes and detected 12 of 12 falls.
- The live cloud demo runs the same code as the laptop agent; decisions took a median of 7.6 s on AWS Lambda.

## What we learned
- Calibration quality decided the accuracy of everything after it, so we measure the camera before trusting it.
- The orientation of one marker wobbles by degrees. Averaging over markers and frames turned 1.5–3.6 cm jumps into
  ±0.1 cm in a synthetic test.
- Locking the protocol before the data mattered. Our evaluation failed one criterion, and that result showed us
  where the model is wrong and that a static check is a strong baseline.
- When the camera cannot tell what happened, the agent asks the person instead of guessing.

## What's next
From the follow-up work in our report:
- A dedicated set of trials in the near-edge band (centre-of-mass margin +0.5 to +2.5 cm), where the model
  under-predicts falls, split by two and three boxes.
- Measure box-on-box and box-on-floor friction with a tilt test.
- Model how a box is released (a small random push or tilt when it is let go).
- Then lock new settings and test them on new trials again.
- Later: more box types and real loads, marker-free box detection, a supervisor dashboard on top of the CloudWatch
  log.

## Built with
OpenCV 5 (`opencv-python` 5.0.0.93, ArUco, ChArUco, solvePnP), Python 3.12, NumPy 2.5.3, MuJoCo 3.15.0, AWS Lambda
(container image), Amazon ECR, Lambda Function URL, Amazon CloudWatch Logs, AWS Budgets, Docker, pytest 9.1.1,
HTML/CSS/JavaScript, Mermaid.

## Sources
1. U.S. Bureau of Labor Statistics, Injuries, illnesses, and fatalities in transportation and warehousing, 2016–20.
   https://www.bls.gov/iif/snapshots/isn-transportation-and-warehousing-2016-20.htm
2. U.S. OSHA, 29 CFR 1910.176(b). https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.176
3. Oregon OSHA, Resource newsletter, 20 Nov 2025, unstable loads.
   https://osha.oregon.gov/pubs/newsletters/resource/2025/Pages/2511-unstable-loads.aspx
