# Drystone

**Predict before you stack.** One camera and OpenCV 5 read where each box is (ArUco markers plus a catalogue of
box sizes and weights) and build a digital twin of the stack. A MuJoCo Monte Carlo simulation estimates the
chance that the stack falls for the next box's planned position. An agent then guides the placement, asks a
supervisor, or rejects it and suggests a safer spot. After the box is placed, it checks the stack again.

> Drystone is a prototype decision-support tool, **not a certified safety device**. A person always makes the
> final call.

Built for the OpenCV AI Competition 2026.

## Live demo for judges
The link to the live page is on our Devpost submission page. The page runs on AWS Lambda (ap-southeast-1).
- Pick a sample photo and move the slider to choose where the next box goes.
- **Shift** = how far the next box sits to the right of the box directly below it, in whole cm (−16 to +16).
- The page shows the photo with the detected markers and the box outlines, P(fall) with its zone, the agent's
  action and suggested spot, and a numbered trace of each step with its time.
- YELLOW: approve, use the suggestion, or reject. RED: use the suggestion, override (name and reason
  required), or cancel. **Use suggestion** moves the box to the suggested spot and checks it again.
  An override is only logged; it never changes the result.
- The first request after a quiet period starts the server and can take about 10 seconds.
- There is no photo upload. The service is calibrated for one camera (our laptop webcam, 1280×720).

## Agent rules
| P(fall) | Zone | Action |
|---|---|---|
| under 10% | GREEN | GUIDE: show where to place the box |
| 10–50% | YELLOW | ASK_SUPERVISOR: approve / use suggestion / reject |
| over 50% | RED | REJECT and suggest the nearest safe spot; going on needs an override with a name and reason |

- P(fall) always comes from many simulations, with 1 cm position and 2 cm load-centre uncertainty. Near a zone
  line the agent runs more simulations; if still unsure, it takes the safer zone.
- Suggested spots must pass 150 simulations before they are called GREEN, and the spot 1 cm further out must
  be GREEN too, so the suggestion stays green even if the box lands 1 cm further out (real placements in our
  practice landed 0.0-1.3 cm off the plan).
- All decision rules live in `tools/drystone_core.py`. The laptop agent and the AWS service both call it.
  Safety decisions are deterministic code and are logged; no language model decides anything.

## How it runs
- `tools/agent.py`: live agent on the laptop (camera, wireframe of the next box, approvals and overrides,
  check after placement, JSONL log). With `--aws` the decisions are computed on Lambda.
- `tools/service.py`: AWS Lambda handler (container image, see `aws/`). One Function URL serves the judges'
  page, the sample photos, decisions for the samples, the supervisor log (one JSON line per choice in
  CloudWatch Logs), and the photo API used by the agent.
- Public endpoint limits: request body ≤ 16 KB for the page (≤ 2 MB for photos), about 20 decisions per
  minute per IP, and identical requests answered from an in-memory cache (marked "cached").

## Run it locally
Windows, Python 3.12:

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements-dev.txt
    python tools/web_local.py

Open http://127.0.0.1:8000/. Run the tests with `python -m pytest tests -q`.

## Results so far
- Camera calibration (laptop webcam, 1280×720): RMS reprojection error 0.37 px over 61 views.
- Position from markers (Test 1): random error RMS 0.18 cm, max 0.47 cm.
- Prediction vs reality (Test 2, 11 counted trials with 2–3 real boxes): 9 of 11 correct (82%), Brier score
  0.145, no fall in the GREEN zone with the current uncertainty settings. Those settings were tuned on the same
  trials, so a new evaluation run is planned.

## Repository
- `tools/`: calibration, tests, decision core, agent, service, local web server, sample photo capture
- `web/`: judges' page (`index.html`) and sample photos (`samples/`)
- `aws/`: Dockerfile and Lambda requirements
- `config/boxes.json`: box catalogue by marker ID
- `data/`: calibration and test results (CSV)
- `tests/`: tests for the web endpoint
