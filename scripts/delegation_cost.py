"""Cost scenario for docs/delegation.md, section 9. INFERRED, list-price arithmetic only."""
OPUS = 11.42  # FOUND: Opus 5.5 USD per task, AA Coding Agent Index at max effort
# INFERRED: other engines scaled from Opus 5.5 by list price (in/out) at equal tokens
RATIO = {"haiku": 0.10 / 4, "terra": 1 / 4, "sonnet": 2 / 4}  # same ratio on input and output
cost = {k: OPUS * v for k, v in RATIO.items()}
cost["opus"] = OPUS

N = {"T0": 45, "T1": 35, "T2": 15, "T3": 5}
BUILD = {"T0": "haiku", "T1": "terra", "T2": "sonnet", "T3": "opus"}
# T3: Opus plans and reviews (one full Opus task, assumed) and a T1 engine builds
unit = {"T0": cost["haiku"], "T1": cost["terra"], "T2": cost["sonnet"], "T3": cost["opus"] + cost["terra"]}
REWORK = 0.30  # share of T0 and T1 tasks that fail once and escalate one tier
extra = {"T0": REWORK * N["T0"] * cost["terra"], "T1": REWORK * N["T1"] * cost["sonnet"], "T2": 0.0, "T3": 0.0}

parts = {c: N[c] * unit[c] + extra[c] for c in N}
routed = sum(parts.values())
all_opus = sum(N.values()) * OPUS

print("class  tasks  unit_usd  rework_usd  total_usd")
for c in N:
    print(f"{c}     {N[c]:>5}  {unit[c]:>8.2f}  {extra[c]:>10.2f}  {parts[c]:>9.2f}")
print(f"All Opus 5.5 : {all_opus:.2f} USD per day")
print(f"Routed       : {routed:.2f} USD per day")
print(f"Saving       : {100 * (all_opus - routed) / all_opus:.1f}%")

assert sum(N.values()) == 100
assert routed < all_opus
assert abs(routed - (sum(N[c] * unit[c] for c in N) + sum(extra.values()))) < 1e-9
assert abs(all_opus - 100 * OPUS) < 1e-9
