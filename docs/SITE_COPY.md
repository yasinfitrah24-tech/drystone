# Drystone: website copy

The source for the text of the judges' page (`web/index.html`, five tabs). Bracketed parts were filled from
`docs/REPORT.md`, `README.md`, `aws/README.md`, `data/eval_report/` or a recorded API answer; the notes at the end list
where the page follows REPORT or the code instead of the draft.

## GLOBAL
- Browser tab title: Drystone · Every stack is a drystone wall
- Meta description: Drystone reads a box stack with OpenCV 5, simulates the next box on AWS Lambda, and tells you to place it, ask, or move it.
- Menu: Home · How it works · Demo · Evidence · Setup, then two icons: Video, GitHub

## HOME
### Hero
- H1: Every stack is a drystone wall.
- Accent: Nothing holds it but placement.
- Body: Drystone checks where the next box goes, then tells you to place it, ask, or move it.
- Buttons: Try the demo · View report
- Hero card (recorded answer for s1 +16 cm, `tools/service.py`, seed 0; same answer live on Lambda):
  - next box → +16 cm [badge: real check]
  - RED · move it — P(fall) 73%
  - overhang: 55% of the box below
  - 150 simulated placements on AWS Lambda
  - [box] Safer spot: +10 cm · still green 1 cm further out (5%)
  - Replay of a real check · OpenCV 5 · MuJoCo

### Problem
- Eyebrow: THE PROBLEM
- H2: Stacks are still built by eye.
- Accent: One guess per box.
- Body: Boxes have no mortar either. Whether a stack stays up depends on where each box lands, and that call is usually made in a second, by eye, with the next box already in hand.
- Three numbers:
  - 99,800 · injuries with days away from work in US transportation and warehousing (2020)
  - 12,100 · of them "struck by object or equipment", a category broader than falling stacks
  - 65 · fatal injuries from "contact with objects and equipment" in 2020 (62–75 a year, 2016–2020)
- Source: U.S. Bureau of Labor Statistics, *Injuries, illnesses, and fatalities in transportation and warehousing,
  2016–20*. https://www.bls.gov/iif/snapshots/isn-transportation-and-warehousing-2016-20.htm

### Short evidence
- H2: Tested on 25 real stacks.
- Accent: Real boxes. Real falls.
- Big number: 0/8 · GREEN placements that fell
- Side: 8/8 · RED placements that fell / 25/25 · placements checked correctly afterwards
- Honest line: One miss we report up front: 4 of 9 YELLOW placements fell. Where the wall cracks → (#evidence)
- Small note: Protocol locked in git (8a953e4) before the first trial · numbers from data/eval_report/

### No mortar
- Eyebrow: BUILT WITH OPENCV 5 + AWS
- H2: No mortar. No black box.
- Accent: Every joint is visible.
- Left panel "Fixed rules decide":
  - Under 10%: GREEN, place it
  - 10–50%: YELLOW, a supervisor approves, takes the safer spot, or rejects
  - Over 50%: RED, refuse and suggest a safer spot
  - Overrides need a name and a reason, and never change the decision
  - No language model makes the safety call
- Right cards:
  - OpenCV 5: Calibrated camera, ArUco markers, pose averaged over 10 frames.
  - MuJoCo: 150 to 600 simulated placements per check, with 1 cm position and 2 cm load uncertainty.
  - AWS Lambda: Same decision code as the laptop agent. Supervisor choices logged in CloudWatch.
- Mono line: 53 tests · 25 locked trials · every decision logged

### Closing band
The camera measures. The simulation estimates. The rules decide. The supervisor signs.

## HOW IT WORKS
- Eyebrow: HOW IT WORKS
- H1: Five checks before the next stone.
- Accent: One loop per box.
- Body: A laptop camera watches the stack. For every new box, Drystone runs the same loop, and what the camera sees changes what happens next: a shifted box is re-checked, a fallen box is re-planned.
- Five checkpoints, as an icon pipeline (icon · number · title · one short line; Decide highlighted). The OpenCV and MuJoCo marks are redrawn as inline SVG; "Twin" is the digital twin (a concept, not a company), so it keeps a cube icon:
  - [OpenCV logo] 01 Perceive · OpenCV 5, 10 frames
  - [cube] 02 Twin · Marker poses + box sizes
  - [MuJoCo logo] 03 Simulate · 150–600 MuJoCo placements
  - [traffic light] 04 Decide · place it · ask · move it
  - [check] 05 Check · OK · OFF_PLAN · FELL

### After a RED
- Eyebrow: AFTER A RED
- H2: RED is a detour, not a dead end.
- Accent: Not +16 cm. Try +10.
- Line: Every RED comes with the nearest safer spot. Margin, overrides and what happens after a fall are rules MARGIN, OVERRIDE, NOT VISIBLE and FELL in the table below.

### Toggle
- H2: You see boxes.
- Accent: Drystone sees a wall.
- Toggle: Photo · what you see / Twin · what Drystone reads
- Caption: Each 80 mm marker gives a box's position and rotation. With the measured box sizes, that is enough to rebuild the stack and test the next box before anyone lifts it.

### Rules table
- H2: Ten rules, written as code.
- Body: Physics gives a probability. These rules turn it into an action, the same way every time.
- Columns: Rule | When | What happens
  - GREEN | P(fall) under 10% | Place it: guide the box in
  - YELLOW | P(fall) 10–50% | Ask: a supervisor approves, takes the safer spot, or rejects
  - RED | P(fall) over 50% | Move it: refuse and suggest a safer spot
  - MARGIN | Every suggested spot | Must stay GREEN 1 cm further out
  - MORE SIMS | Near 10% or 50% | Simulate more (150 → 300 → 600); if still unclear, take the safer zone
  - OVERRIDE | Going ahead on YELLOW or RED | Name (2–60 characters) and reason (5+ characters), logged; the zone never changes
  - RETAKE | Base marker unreadable or reading unsteady | Up to 3 fresh readings
  - NOT VISIBLE | Placed box not seen | Ask: fell, or not placed yet?
  - FELL | Box gone after placement | Pick it up, plan the same box again
  - SETUP GATE | Evaluation mode, setup off by more than 1.5 cm | Refuse until fixed

### Diagrams
- H2: The whole system, on one page.
- Architecture caption: Laptop agent with OpenCV 5, AWS Lambda running the same decision code, CloudWatch logs and a zero-spend budget alarm.
- Agent loop caption: Perceive, twin, simulate, decide, act, check, and what happens when perception fails.

### Closing
Place it once. Place it right. [button: Try the demo →]

## DEMO
- Eyebrow: DEMO
- H1: Try a placement.
- Accent: No camera needed.
- Body: Pick a real photo from our test stack, choose where the next box goes, and the same code that runs the laptop agent decides, live on AWS Lambda.
- Note: The first check can take ~10 s while the server wakes up. Supervisor choices are logged without your IP address.
- Photo labels: s1 · One box / s2 · Two boxes, aligned / s3 · Two boxes, top one shifted
- Ruler: Where should the next box go? (sub: cm to the right of the box below)
- Free shift: Or pick any shift · [–] +16 cm (55% overhang) [+] · Check
- Legend: GREEN <10% · place it / YELLOW 10–50% · ask / RED >50% · move it
- Loading: Simulating the next box on AWS Lambda… (sub: Up to 600 simulated placements. Photo and ruler are locked until it answers.)
- GREEN result: Place it. Drystone guides the box to +X cm, then checks it landed as planned.
- YELLOW result: Ask a supervisor. Approve, take the safer spot (+X cm, Y%), or reject. The choice is logged; the zone stays YELLOW.
- RED result: Move it. Refused at +X cm. Try +Y cm: it stays green even if the box lands 1 cm further out (Z% there).
- RED override note: Going ahead anyway needs a name and a reason. It is logged, and the decision stays RED.
- Error: The simulator didn't answer. Nothing was decided, and your photo and spot are kept. [button: Try again]
- Rate limit: Too many checks from your network this minute. Wait a moment, then try again.
- Trace title: How it decided

## EVIDENCE
- Eyebrow: EVIDENCE
- H1: 25 real stacks.
- Accent: Locked before the first box moved.
- Body: The test plan, all 25 setups and the pass criteria went into git before any trial ran (commit 8a953e4). We ran all 25 and report every result.
- Table (Criterion | What it asks | Result):
  - C1 | No GREEN placement falls | 0 of 8 fell · PASS
  - C2a | At least 85% right on clear cases (P < 10% or > 70%) | 14 of 14 · PASS
  - C2b | Total falls inside the model's 90% band | 12 fell; 8.5 predicted (band 5.6–11.5) · FAIL
  - C3 | Brier score at most 0.20 | 0.125 · PASS
  - C4 | At least 20 valid trials | 25 trials with an outcome · PASS

### Where it failed
- H2: Where the wall cracks.
- Accent: Reported, not patched.
- Cards:
  - YELLOW is riskier than its number · 4 of 9 YELLOW placements fell, while the model gave them 25% on average. In a narrow middle band of overhang, 4 of 8 trials fell (T16, T17, T01, T25). Treat YELLOW as more dangerous than its number says.
  - No quiet fixes · After the run we searched simulator settings for one that closes the gap. None did, so Drystone stays exactly as tested.
  - A simple rule is just as accurate · A static tipping check also gets 84% right on these trials. Drystone's edge is calibration (Brier 0.125 vs 0.160), not more hits.

### Agent behaviour
- H2: The agent, under test.
- Numbers: 25/25 placements checked correctly afterwards · 12/12 falls detected (7/7 in rehearsal) · 4 setups refused until fixed · 0 retakes, 0 fallbacks

### Limits
- H2: Limits and responsible use.
  - Tested on three identical 1 kg boxes (29 × 17 × ~19.5 cm), one floor, one laptop camera.
  - Every box needs a printed ArUco marker.
  - A decision aid prototype, not a certified safety device.
  - Photos show boxes only, no faces.
- Link: Full report & failure cases → (via LINKS)

## SETUP
(The five ways are options, not steps, so each has an icon instead of a number.)
- Eyebrow: SETUP
- H1: Lay the first stone.
- Accent: Start with zero install. End with a real camera.
- Body: Pinned versions throughout (Python 3.12, OpenCV 5.0, MuJoCo 3.15). Every command below is copied from the README.
- [icon: globe] No install · The Demo tab runs the full decision on AWS Lambda with three real photos. [link: Open the demo →]
- [icon: laptop] On your laptop, with our photos · Clone the repo, install, and run the same page locally. [code from README, copy button]
- [icon: camera] The full agent: camera + markers · You need a webcam, printed ArUco markers (DICT_4X4_50, 80 mm, IDs 0–2), a ChArUco board on something rigid and flat, and boxes listed in config/boxes.json. Measure what you printed. A calibration is only used if it passes the built-in quality check. [calibration + agent code from README; Lambda URL as <your-function-url>]
- [icon: cloud] Your own AWS Lambda · Build the container, push it to ECR, and put a Lambda Function URL in front of it. Set a budget alarm first. Full steps are in aws/README.md. [short code from aws/README.md, account as <account>]
- [icon: shield with check] Check our work · Run the test suite and rebuild the evaluation summary from the raw trials. [pytest + eval_report code from README]

## FOOTER
- Drystone · a decision aid prototype for box stacking, not a certified safety device.
- Built by Yasin & Vincent for the OpenCV AI Competition 2026 · OpenCV 5 · MuJoCo · AWS Lambda
- MIT License (Video and GitHub are icons in the header; the report is the hero button "View report"; all via LINKS)

## Notes: where the page follows REPORT or the code instead of this draft
1. Problem, first number: REPORT §1 says "99,800 nonfatal cases with days away from work", not "injuries". The page
   says "nonfatal cases".
2. Rules table, OVERRIDE: in the code a YELLOW placement goes ahead by approval (name optional on the page), not by an
   override; only RED needs an override with a name (2–60 characters) and a reason (5–300 characters). The page says
   "Going ahead on RED"; YELLOW approval is in the YELLOW row.
3. Rules table, RETAKE: the code retakes when the base marker is not visible, the visible markers change between
   frames, a box jitters more than 1 cm, or a box is turned more than 12°; after 3 readings it asks the person. The
   page says this.
4. Evidence, failure card: REPORT §7.4 describes the middle band by centre-of-mass margin (+0.5 to +2.5 cm), not by
   overhang. The page says "centre-of-mass margin". The four trials that fell are T16, T17, T01, T25.
5. Evidence, limits: REPORT §9 gives the box height as 19.4–19.6 cm; the page uses that.
6. Setup, body: the commands come from README.md and aws/README.md; `git clone` and `cd drystone` are not in the
   README. The page says so.
7. Setup, step 05: the raw evaluation logs are not published (their photos show people). `tools/eval_report.py`
   rebuilds the summary from an evaluation log; the published `data/eval_report/trials.csv` holds every per-trial
   number. The page says so.
8. Demo note: the page test checks the loading text; it now reads "can take ~10 s" (tests/test_web.py updated).

## Duplicates removed (19 Oct, approved by Yasin)
1. How it works: the three After-a-RED cards repeated rules MARGIN, OVERRIDE, NOT VISIBLE and FELL; replaced by one line pointing to the table.
2. Home hero card: "Fixed rules, not a language model" repeated the rules panel; now "Replay of a real check · OpenCV 5 · MuJoCo".
3. Home hero card: the "Try it yourself →" link repeated the "Try the demo" button; removed.
4. Evidence C4: "25 of 25" looked like the 25/25 check result; now "25 trials with an outcome".
6. Evidence limits: the override line was already on Home and How it works; removed.
7. "Logged without IP addresses" kept only on the Demo tab (removed from the Home AWS card and Evidence limits).
8. Evidence limits: "No language model" was already on Home; removed (same line as 6).
Kept on purpose: zone bands on Home, How it works and the Demo legend; the safety disclaimer in Evidence and the footer; the Home evidence summary; 150–600 simulations and 10 frames on Home and How it works; the Setup option "No install".
