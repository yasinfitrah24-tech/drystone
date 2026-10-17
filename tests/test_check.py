"""Check after a placement, on synthetic photos: a box that fell next to the stack is FELL, not a retake.

Each case runs the laptop path (read_scene + drystone_core.verify) and the Lambda path (service, mode "check",
photos as agent.py --aws sends them).
    python -m pytest tests/test_check.py -q
"""
import base64
import json

import cv2
import pytest

import drystone_core as core
import service
import synth_scene as S
from agent import read_scene, read_stack

H = [S.CATALOG[i]["H"] for i in range(3)]
Y = [0.0, S.FLOOR_Y + H[0] + H[1] / 2, S.FLOOR_Y + H[0] + H[1] + H[2] / 2]     # marker heights when stacked
OFFSET = 0.06                                                                    # planned shift of ID 2 (m)


def stack01():
    return [S.upright(0, 0.0, y=Y[0]), S.upright(1, 0.0, y=Y[1])]


def read(img, n=10):
    s = service._setup()
    return read_scene(service._Frames([img] * n), s["detector"], s["catalog"], s["obj"], s["K"], s["dist"], 0, n=n)


@pytest.fixture(scope="module")
def plan():
    stack, loose, *_, problem = read(S.render(stack01()))
    assert problem is None and not loose and [b["id"] for b in stack] == [0, 1]
    return {"before": stack, "box": core.candidate_box(stack, 2, OFFSET, S.CATALOG)}


def fell_upright_beside():
    return stack01() + [S.upright(2, 0.40, y=S.FLOOR_Y + H[2] / 2, z_front=-0.03)]


def fell_lying_beside():
    return stack01() + [S.lying_on_side(2, 0.36, z_front=-0.02)]


def fell_out_of_view():
    return stack01()


def placed_as_planned():
    return stack01() + [S.upright(2, OFFSET, y=Y[2])]


def placed_3cm_off():
    return stack01() + [S.upright(2, OFFSET + 0.03, y=Y[2])]


CASES = [("a: fell, upright beside", fell_upright_beside, "FELL", "on the floor next to the stack"),
         ("b: fell, lying beside", fell_lying_beside, "FELL", "on the floor next to the stack"),
         ("c: fell out of view", fell_out_of_view, "FELL", "not visible -> it likely fell out of view"),
         ("d: placed as planned", placed_as_planned, "OK", "as planned"),
         ("e: placed 3 cm off", placed_3cm_off, "OFF_PLAN", "cm from the plan -> risk recomputed")]


@pytest.mark.parametrize("name,scene,status,text", CASES, ids=[c[0][:1] for c in CASES])
def test_check_laptop(plan, name, scene, status, text):
    stack, loose, *_, problem = read(S.render(scene()))
    assert problem is None, f"{name}: the check must not ask for a retake ({problem})"
    v = core.verify(plan["before"], stack, plan["box"], S.CATALOG, loose=loose)
    assert v["status"] == status, v
    assert text in v["message"]
    if status == "OFF_PLAN":
        assert 0.02 < v["deviation_m"] < 0.04                  # moved 3 cm: OFF_PLAN, not FELL
    if status == "FELL":
        assert "box ID 2" in v["message"]                      # the box that fell, not another one
        assert [b["id"] for b in stack] == [0, 1]


def _cm(b):
    return {"id": int(b["id"]), "x_cm": b["x"] * 100, "y_cm": b["y"] * 100, "z_cm": b["z"] * 100}


@pytest.mark.parametrize("name,scene,status,text", CASES, ids=[c[0][:1] for c in CASES])
def test_check_lambda(plan, name, scene, status, text):
    jpg = base64.b64encode(cv2.imencode(".jpg", S.render(scene()), [cv2.IMWRITE_JPEG_QUALITY, 92])[1]).decode()
    body = {"mode": "check", "images": [jpg] * 3, "return_image": False,
            "plan": {"before": [_cm(b) for b in plan["before"]], "box": _cm(plan["box"])}}
    out = service.lambda_handler(body)
    r = json.loads(out["body"])
    assert out["statusCode"] == 200 and r.get("action") != "RETAKE", r.get("problem")
    assert r["verify"]["status"] == status, r["verify"]
    assert text in r["verify"]["message"]
    if status == "OFF_PLAN":
        assert 2 < r["verify"]["deviation_cm"] < 4
    if status == "FELL":
        assert r["action"] == "STOP"
        assert [b["id"] for b in r["stack"]] == [0, 1]


@pytest.mark.parametrize("yaw", [0, -35])
def test_decision_names_the_right_box_and_keeps_the_stack_frame(yaw):
    """A fallen, turned box beside the stack: the decision reading names it (not ID 1), and it does not
    tilt the frame of the stack (it used to: 16 deg for a box turned 50 deg)."""
    fallen = S.upright(2, 0.33, y=S.FLOOR_Y + H[2] / 2, z_front=-0.08)
    fallen["R"] = S.rot_y(yaw)
    s = service._setup()
    img = S.render(stack01() + [fallen])
    stack, *_, problem = read_stack(service._Frames([img] * 10), s["detector"], s["catalog"], s["obj"], s["K"],
                                    s["dist"], 0, n=10)
    assert problem == "box ID 2 is on the floor next to the stack, not on it -> move it out of the camera view"
    assert [b["id"] for b in stack] == [0, 1]
    assert abs(stack[1]["x"]) < 0.005 and abs(stack[1]["y"] - Y[1]) < 0.01


def test_box_held_above_the_stack_is_a_gap_not_fell(plan):
    """A box still in the air above the stack (not let go yet) is reported, not counted as fallen onto the floor."""
    stack, loose, *_ = read(S.render(stack01() + [S.upright(2, OFFSET, y=Y[2] + 0.08)]))
    assert [b["id"] for b in stack] == [0, 1] and loose[0]["where"] == "gap"
    v = core.verify(plan["before"], stack, plan["box"], S.CATALOG, loose=loose)
    assert v["status"] == "FELL" and "above the stack but not resting on it" in v["message"]
