# Drystone: website copy

The source for the text of the judges' page (`web/index.html`, five tabs). Bracketed parts were filled from
`docs/REPORT.md`, `README.md`, `aws/README.md`, `data/eval_report/` or a recorded API answer; the notes at the end list
where the page follows REPORT or the code instead of the draft.

## GLOBAL
- Browser tab title: Drystone · Every stack is a drystone wall
- Meta description: Drystone reads a box stack with OpenCV 5, simulates the next box on AWS Lambda, and tells you to place it, ask, or move it.
- Menu: Home · How it works · Demo · Evidence · Setup, then two icons: Video, GitHub
- Links (View report, Full report & failure cases, Video, GitHub) are hidden while their `LINKS` value is empty or "#", and appear by themselves once it is filled.
- After a tab change, focus moves to that tab's H1.
- How it works pipeline (motion like the Subtext site, in Drystone blue): the five checks rise in one by one the first time the tab is seen, each circle glows in turn (6 s cycle), and the dashed connectors keep moving toward the next step. Reduced motion or no script: static.
- Big numbers (Problem, Home evidence, Evidence "The agent, under test") count up from 0 the first time they scroll into view, about 1.2 s; the text after a slash stays ("/8"). Reduced motion or no script: the final number shows at once. Screen readers get the final number.

## HOME
### Hero
- H1: Every stack is a drystone wall.
- Accent: Nothing holds it but placement.
- For line: For anyone stacking boxes by hand. One webcam, one printed marker per box.
- Body: Drystone checks where the next box goes, then tells you to place it, ask, or move it.
- Buttons: Check a placement · View report
- Hero card (23 Oct: the Drystone camera screen; recorded answer for s1 +16 cm, `tools/service.py`, seed 0; same answer live on Lambda). Every number comes from the record:
  - Top bar: [blinking dot] REPLAY · s1 · next box → +16 cm [badge: real check]
  - Camera screen with viewfinder corners and a thin grid. Stage label (top left) and counter (top right): SCAN · OpenCV 5 → LOCK · ArUco ID 0 → TWIN · digital twin → SIMULATE · MuJoCo (n/150 sims · fell k) → DECIDE · fixed rules → SUGGEST · +10 cm; counter "camera 1280×720" until the simulation.
  - On the photo: scan line, marker brackets + "ID 0", twin outline, flashing runs (red = fell, green = stood) around +16 cm, the edge of the box below, the centre of mass, "overhang 55%" and "margin −1.5 cm", then the next box in red and the safer spot dashed blue.
  - Decision bar: RED · move it [REJECT] — P(fall) 73% (counts up, then the bar turns red)
  - [dashed box] Safer spot: +10 cm · still green 1 cm further out (5%)
  - Status bar: RED · P(fall) 73% ±7 · suggest +10 cm · 150 sims
  - Motion: the whole replay plays once on load and each time Home is opened (about 8 s), then holds the result; only a faint scan line and the REPLAY dot keep moving. Fell 110 = 73% of 150 from the record; only the order of the flashing runs is illustrative. Reduced motion: the result, no motion.

### Problem
- Eyebrow: THE PROBLEM
- H2: Stacks are still built by eye.
- Accent: One guess per box.
- Body: Boxes have no mortar either. Whether a stack stays up depends on where each box lands, and that call is usually made by eye, with the next box already in hand.
- Three numbers:
  - 99,800 · nonfatal cases with days away from work in US transportation and warehousing (2020)
  - 12,100 · of them "struck by object or equipment", a category broader than falling stacks
  - 65 · fatal injuries from "contact with objects and equipment" in 2020 (62–75 a year, 2016–2020)
- Source: U.S. Bureau of Labor Statistics, *Injuries, illnesses, and fatalities in transportation and warehousing,
  2016–20*. https://www.bls.gov/iif/snapshots/isn-transportation-and-warehousing-2016-20.htm

### Short evidence
- H2: Tested on 25 real stacks.
- Accent: Real boxes. Real falls.
- Big number: 0/8 · GREEN placements that fell
- Side: 8/8 · RED placements that fell / 25/25 · placements checked correctly afterwards
- Honest line: One miss we report up front: 4 of 9 YELLOW placements fell. 1 of 5 locked criteria failed (C2b) → (#evidence)
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
- Mono line: 69 tests · 25 locked trials · every decision logged

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
- Since 23 Oct both are live diagrams on the page (inline SVG; a vertical list on phones), styled like the hero card, each with a small "Open as image" link to the PNG. Tap or hover a node for one line from REPORT. Default line: Tap or hover a step to see what it does.
- Architecture (REPORT section 4 + section 6). Motion: a data packet runs from the webcam to the decision and back through Check; the run alternates between "computed on the laptop" and "--aws: computed on AWS Lambda, same code".
  Nodes (title · sub · tap line):
  - Webcam · 1280×720 / ChArUco calibration · Live agent · tools/agent.py: camera loop, wireframes, human control, JSONL log with photos.
  - OpenCV 5 · ArUco + pose / 10 frames, median · Perception · tools/agent.py (read_scene, build_stack): markers → box poses → the stack, by contact.
  - Digital twin · stack by contact / box catalogue · Perception: the stack is built from the bottom box up, by contact; boxes off the stack are not part of it.
  - MuJoCo · Monte Carlo / 150–600 simulations · Decision core · tools/drystone_core.py: static check, Monte Carlo P(fall), zones, suggestion search.
  - Agent rules · GREEN/YELLOW/RED / 1 cm margin · Decision core: fixed rules turn P(fall) into GUIDE, ASK_SUPERVISOR or REJECT; no language model decides.
  - Supervisor · approve · suggest / override + reason · A person approves a YELLOW placement or rejects it, and can override a RED rejection only with a name and a reason.
  - Box placed · by a person · The agent never moves a box; a person places every one.
  - Check again · OK/OFF_PLAN/FELL · Check after placement (drystone_core.py): the camera reads the stack again and compares it with the plan.
  - Amazon ECR · drystone-service / tag = git commit · The container image lives in Amazon ECR; every deploy is tagged with the git commit hash.
  - AWS Lambda + Function URL · same decision code / container image · 2048 MB · 60 s · Service · tools/service.py: AWS Lambda handler: photo API for the agent, judges' web page and its API.
  - CloudWatch Logs · decisions, / supervisor choices · Supervisor choices are one JSON line in CloudWatch Logs, without the IP address.
  - If AWS fails · the same code runs / on the laptop · If AWS fails, the laptop computes the decision with the same code and logs that it did.
  Step labels: a frame from the webcam · ArUco markers + pose, 10 frames, median · the stack, by contact · 150–600 simulations · zone + suggestion with a 1 cm margin · the supervisor decides · a person places the box · check again: OK / OFF_PLAN / FELL · read the stack again
- Agent loop (REPORT section 8.1, every branch). Motion: one real run, the final practice of 18 Oct (STATUS "Alur video final").
  Nodes (title · sub · tap line):
  - Read the stack · 10 frames · pose / stack by contact · The agent reads the stack; it retakes a shaky reading (up to 3 times).
  - Replan · standing box missing · The agent notices a changed stack ("stack changed: ID 1 is missing") and plans in ID order.
  - Decide · P(fall) + zone / on Lambda or laptop · The agent computes P(fall), zone and the action; it runs more simulations near a zone line and takes the safer zone if unsure.
  - Guide · GREEN · GREEN → GUIDE: place the box in the outline, no approval needed.
  - Ask · YELLOW · reject → Read · A person approves a YELLOW placement (or uses the suggestion), or rejects it.
  - Reject · RED · cancel → Read · The agent searches the nearest safe spot with a 1 cm margin; a person uses it, or overrides with a name and a reason.
  - Place · worker places it, SPACE · A person places every box, then presses SPACE.
  - Check · compare with the plan · The agent checks the result: OK / OFF_PLAN / FELL.
  - Warn · OFF_PLAN: > 1.5 cm off · After an OFF_PLAN placement the risk is computed again; fix it if it is not green.
  - Ask f / p · not visible, stack intact · A person answers f (it fell out of view) or p (not placed yet, look again).
  - Fell · on the floor / gone · The agent plans a fallen box again; a person picks it up and keeps it out of view.
  - Wait · tell the worker · A box off the stack or a wrong setup: one message, no automatic retake; the worker fixes it and presses SPACE.
  Step labels: 1 · box ID 1 at +6 cm, SPACE · decide on Lambda: GREEN 0% (5.0 s) · GREEN → GUIDE: green outline · box ID 1 placed · check: OK (−0.4 cm), stack GREEN · 2 · box ID 2 at +18 cm, SPACE · decide: RED 93% (Lambda 10.0 s) · RED → REJECT · suggestion +9 cm (1%) · override: name + reason, logged · placed at +18 cm, the box fell · FELL: box ID 2 is on the floor next to the stack · pick it up, keep it out of view, SPACE · planning box ID 2 again after it fell · decide again: RED 93%, suggestion +9 cm · use suggestion: green outline at +9 cm · box ID 2 placed at +9 cm · check: OK (−0.3 cm), stack GREEN 1% · final practice, 18 Oct · decisions 3 · override 1 · fell 1
- Reduced motion or no script: both diagrams static, every node readable.

### Closing
Place it once. Place it right. [button: Try the demo →]

## DEMO
- Eyebrow: DEMO
- H1: Try a placement.
- Accent: No camera needed.
- Body: Pick a real photo from our test stack, choose where the next box goes, and the same code that runs the laptop agent decides, live on AWS Lambda.
- Note: The first check can take up to 10 s while the server wakes up. Supervisor choices are logged without your IP address.
- Photo labels: s1 · One box / s2 · Two boxes, aligned / s3 · Two boxes, top one shifted
- Shift control (draft 23 Oct, a slider in place of the ruler and the − / + row): Where should the next box go? (sub: cm from the box below: − left, + right). Example chips from the photo, to the left (−16 RED, −13 YELLOW, −9/−10 SUGGESTED, −6 GREEN) and to the right (GREEN, SUGGESTED, YELLOW, RED as before), each side as its own group; a tap moves the slider there, then one slider −16…+16 cm on a neutral blue track (ticks every 1 cm, numbers every 4 cm, coloured pins at the examples) with a value bubble on the handle. Picking a spot never runs a check: the ghost box and the bubble follow the slider or the chip. Only the button runs it, labelled with the spot ("Check +X cm"), or Enter on the slider. Under the slider: "+X cm · Y% overhang" and that button. Moving the slider after a result clears it back to the ghost box.
- Ghost box: while a shift is picked and not checked yet (ruler, drag, − / +), the photo shows the next box at that shift as a dashed grey outline, and a dashed chip at the bottom left of the photo says "next box +X cm · not checked yet". No zone colour until Check; the outline is the same one the service draws after the check (`tools/ghost_boxes.py`).
- Legend: GREEN <10% · place it / YELLOW 10–50% · ask / RED >50% · move it
- Start card: Pick a spot with the slider or an example, then press Check. (The quick button "Check +X cm" for the YELLOW example stays; its hint says "example", not "marker".)
- Loading: Simulating the next box on AWS Lambda… (sub: Up to 600 simulated placements. Photo and slider are locked until it answers.)
- Loading, after 8 s: The server is waking up. The first check can take up to 10 s.
- GREEN result: Place it. Drystone guides the box to +X cm, then checks it landed as planned.
- YELLOW result: Ask a supervisor. Approve, take the safer spot (+X cm, Y%), or reject. The choice is logged; the zone stays YELLOW.
- RED result: Move it. Refused at +X cm. Try +Y cm: it stays green even if the box lands 1 cm further out (+Y+1 cm: Z%).
- RED override note: Going ahead anyway needs a name and a reason. It is logged, and the decision stays RED.
- Override errors, under each field: Add the supervisor's name (at least 2 characters). / Add a reason (at least 5 characters).
- After a supervisor choice is logged, Approve / Reject / Override / Cancel are locked until the next check.
- Error: The simulator didn't answer. Nothing was decided, and your photo and spot are kept. [button: Try again]
- Rate limit: Too many checks from your network this minute. Wait a moment, then try again.
- Trace title: How it decided

## EVIDENCE
- Eyebrow: EVIDENCE
- H1: 25 real stacks.
- Accent: Locked before the first box moved.
- Body: The test plan, all 25 setups and the pass criteria went into git before any trial ran (commit 8a953e4). We ran all 25 and report every result.
- Verdict line, above the table: Verdict: FAIL on 1 of 5 locked criteria. C2b missed by one fall (12 against a band of 6–11). No box fell in the GREEN zone.
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
- OS note: Where Windows and macOS/Linux differ, both are shown. Each command was run in a fresh clone on Windows cmd.
- [icon: globe] No install · The Demo tab runs the full decision on AWS Lambda with three real photos. [link: Open the demo →]
- [icon: laptop] On your laptop, with our photos · Clone the repo, make a Python 3.12 environment, install, and run the same page locally. [Before you start: Git, and Python 3.12 (on Windows, `py -3.12` needs Python 3.12 installed from python.org). Then the commands, git clone always first: `git clone <repository URL>` while LINKS.repo is empty, with the note "Repository link: on the submission page."; `git clone <LINKS.repo>.git` once it is filled. Then cd drystone; Windows (cmd): py -3.12 -m venv .venv, .venv\Scripts\activate; macOS / Linux: python3.12 -m venv .venv, source .venv/bin/activate; then pip install -r requirements-dev.txt (includes requirements.txt and adds pytest), python tools/web_local.py; "Then open http://127.0.0.1:8000/ (the address it prints; another port: --port 8080)."]
- [icon: camera] The full agent: camera + markers · You need a webcam, printed ArUco markers (DICT_4X4_50, 80 mm, IDs 0–2), a ChArUco board on something rigid and flat, and boxes listed in config/boxes.json. Measure what you printed. A calibration is only used if it passes the built-in quality check. ["Print both sheets at 100% (actual size), not fit to page." While the PDF links are empty: "The PDFs are in the repository: docs/print/markers_A4.pdf … and docs/print/charuco_A4.pdf …". "Calibrate your camera. Measure one printed square and use your own name. Repeat until the verdict is LAYAK (passes); it then saves data/camera_mycam.yaml. data/camera_laptop.yaml is our own webcam; calibrate yours." Code: calibrate.py --name mycam --square-mm <your measured square> --auto; agent.py --calib data/camera_mycam.yaml. AWS: "The Lambda image uses the calibration in data/camera_laptop.yaml, so put yours in that file before you build it." Windows (cmd): set DRYSTONE_URL=<your-function-url>, --aws %DRYSTONE_URL%; macOS / Linux: export DRYSTONE_URL=…, --aws "$DRYSTONE_URL"]
  - Links (via LINKS `markers` and `board`, GitHub file links, filled on Monday; hidden until then): Download printable markers (PDF) → `docs/print/markers_A4.pdf` · Download calibration board (PDF) → `docs/print/charuco_A4.pdf`. Both made by `tools/make_print_sheets.py`.
- [icon: cloud] Your own AWS Lambda · Build the container, push it to ECR, and put a Lambda Function URL in front of it. Region ap-southeast-1; write your AWS account ID where it says <account>. Full steps are in aws/README.md. [Before you start: Docker Desktop (running) and AWS CLI v2. First-time setup (from aws/README.md): 1 zero-spend budget with an email alert, 2 `aws configure`: an access key of your own IAM user with ECR and Lambda permissions, region ap-southeast-1, 3 aws ecr create-repository, 4 build, tag and push the image: the build → tag → push commands under Update (up to docker push), 5 Lambda console → Create function → Container image, function name `drystone` (the Update commands use --function-name drystone) → drystone-service with your tag → x86_64; memory 2048 MB, timeout 60 s, 6 Function URL auth NONE, CORS POST, URL kept in DRYSTONE_URL. Update: Windows (cmd) and macOS / Linux blocks, tagged with the commit hash, account as <account>]
- [icon: shield with check] Check our work · Run the test suite, and rebuild the evaluation summary from the published per-trial table, data/eval_report/trials.csv. It writes data/eval_report/from_trials/summary.md, the same as our summary.md except its first line. Our raw logs stay on our laptop (their photos show people). [python -m pytest tests -q · python tools/eval_report.py --trials data/eval_report/trials.csv]

## FOOTER
- Drystone · a decision aid prototype for box stacking, not a certified safety device.
- Built by Yasin & Vincent for the OpenCV AI Competition 2026 · OpenCV 5 · MuJoCo · AWS Lambda
- MIT License (Video and GitHub are icons in the header; the report is the hero button "View report"; all via LINKS)

## Notes: where the page follows REPORT or the code instead of this draft
1. Problem, first number: REPORT §1 says "99,800 nonfatal cases with days away from work"; the draft said
   "injuries". This copy now says "nonfatal cases", the same as the page.
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
8. Demo note: the page test checks the loading text; it now reads "can take up to 10 s" (from the cold-start check of 23 Oct; tests/test_web.py updated).

## Duplicates removed (19 Oct, approved by Yasin)
1. How it works: the three After-a-RED cards repeated rules MARGIN, OVERRIDE, NOT VISIBLE and FELL; replaced by one line pointing to the table.
2. Home hero card: "Fixed rules, not a language model" repeated the rules panel; now "Replay of a real check · OpenCV 5 · MuJoCo".
3. Home hero card: the "Try it yourself →" link repeated the "Try the demo" button; removed.
4. Evidence C4: "25 of 25" looked like the 25/25 check result; now "25 trials with an outcome".
6. Evidence limits: the override line was already on Home and How it works; removed.
7. "Logged without IP addresses" kept only on the Demo tab (removed from the Home AWS card and Evidence limits).
8. Evidence limits: "No language model" was already on Home; removed (same line as 6).
Kept on purpose: zone bands on Home, How it works and the Demo legend; the safety disclaimer in Evidence and the footer; the Home evidence summary; 150–600 simulations and 10 frames on Home and How it works; the Setup option "No install".
