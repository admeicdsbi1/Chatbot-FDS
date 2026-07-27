"""
Tests for the numeric-fidelity guard (verify.guard_answer).
Run:  python backend/test_verify.py    (no pytest needed)
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import verify
from verify import guard_answer, PLACEHOLDER

_fails = []


def check(name, cond):
    print(("  ok  " if cond else " FAIL ") + name)
    if not cond:
        _fails.append(name)


CTX = (
    "The speed sensor air gap must be maintained at 0.8 mm to 1.5 mm. "
    "Operating voltage of the WSP control unit is 110 V DC. "
    "The dump valve activation pressure is 3.8 bar. "
    "Tighten the axle-box bolt to a torque of 90 Nm. "
    "Aerosol generator activation temperature is 68 °C. "
    "Fault code 4.3 indicates a speed sensor open circuit. "
    "The WSP relay module part number is MB04, model MGS2. "
    "Standardised MCB rating is 2 A."
)


# --- values present verbatim must pass untouched -----------------------------
def test_confirmed_values_pass():
    ans = ("Set the air gap to 0.8 mm. Supply is 110 V DC and the dump valve "
           "trips at 3.8 bar. Torque the bolt to 90 Nm.")
    clean, stripped = guard_answer(ans, CTX)
    check("confirmed values not stripped", clean == ans and stripped == [])


def test_unit_spacing_normalized():
    ans = "The MCB is rated 2A and the activation temperature is 68°C."
    clean, stripped = guard_answer(ans, CTX)      # ctx has "2 A" and "68 °C"
    check("2A≡2 A and 68°C≡68 °C confirmed", stripped == [])


def test_range_endpoint_confirms():
    ans = "Maintain the air gap between 0.8 and 1.5 mm."
    clean, stripped = guard_answer(ans, CTX)
    check("range endpoints confirmed", stripped == [])


# --- fabricated / altered values must be stripped ----------------------------
def test_hallucinated_value_stripped():
    ans = "Torque the bolt to 120 Nm."          # ctx says 90 Nm
    clean, stripped = guard_answer(ans, CTX)
    check("wrong torque stripped", PLACEHOLDER in clean
          and any(t == "120 Nm" for _, t in stripped))


def test_altered_magnitude_with_present_number_stripped():
    # 0.6 is NOT in ctx as an air gap; guard must not pass it just because
    # other decimals exist.
    ans = "Set the speed sensor air gap to 0.6 mm."
    clean, stripped = guard_answer(ans, CTX)
    check("altered air gap 0.6 mm stripped", PLACEHOLDER in clean)


def test_hallucinated_fault_code_stripped():
    ans = "This is reported as fault code 9.9 on the display."
    clean, stripped = guard_answer(ans, CTX)
    check("bogus fault code stripped", PLACEHOLDER in clean
          and any(k == "fault-code" for k, _ in stripped))


def test_confirmed_fault_code_and_part_pass():
    ans = "Fault code 4.3 points to the speed sensor; replace module MB04 (MGS2)."
    clean, stripped = guard_answer(ans, CTX)
    check("real fault code + part number pass", stripped == [])


def test_hallucinated_part_number_stripped():
    ans = "Replace the unit with part number XY9988-777."
    clean, stripped = guard_answer(ans, CTX)
    check("fake part number stripped", PLACEHOLDER in clean
          and any(k == "part-number" for k, _ in stripped))


# --- things that must NOT be touched -----------------------------------------
def test_step_numbers_untouched():
    ans = ("Follow these steps: 1. Isolate power. 2. Remove the cover. "
           "3. Check the sensor.")
    clean, stripped = guard_answer(ans, CTX)
    check("step numbers not stripped", clean == ans and stripped == [])


def test_reference_block_untouched():
    ans = ("Supply is 110 V DC.\n\n**Reference:** WSP Handbook, Clause 4.3.2, "
           "p.27; RDSO letter dt. 01.10.2024")
    clean, stripped = guard_answer(ans, CTX)
    check("reference block preserved", "Clause 4.3.2, p.27" in clean
          and "01.10.2024" in clean and stripped == [])


def test_empty_inputs():
    check("empty answer safe", guard_answer("", CTX) == ("", []))
    check("empty context safe", guard_answer("x", "") == ("x", []))


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(name)
            fn()
    print()
    if _fails:
        print(f"{len(_fails)} FAILED: {_fails}")
        raise SystemExit(1)
    print("all guard tests passed")
