# Representative Failure Analysis

Measured `main_c5` valid pairs: 122 both pass, 8 MAGE-only pass, 3 routed-only pass, 6 both fail. Rows with `valid_pair=False` are treated separately.

## Prob113_2012_q1g

- Outcome: `routed_only_pass`
- B0 failed with 30/100 mismatches; B1 passed with 0/100.
- B0 final RTL used a simplified expression, `(~x[0]) & (x[2] | ~x[3])`, which appears to misread the K-map variable ordering.
- B1 initially had 67 mismatches, then the logic route rebuilt the output as a row/column K-map `case`; debug history accepted the repair after simulation passed.
- Likely reason: routed repair used mismatch feedback to correct K-map axis/order interpretation that the baseline simplification got wrong.

## Prob028_m2014_q4a

- Outcome: `mage_only_pass`
- B0 passed; B1 failed official golden elaboration because final RTL declared `TopModule_unused`, leaving no `TopModule`.
- B1 route history shows an `ambiguous_runnable` repair: the generated debug TB had its own `TopModule`, causing a duplicate-module compile error. The repair renamed the RTL module and was locally accepted as simulation-passing.
- Likely reason: routed repair overfit to a generated-testbench artifact and broke the required top-level interface for the real golden test.

## Prob070_ece241_2013_q2

- Outcome: `both_fail`
- B0 failed with 10/107 mismatches; B1 failed with 3/107.
- Both implementations handled the required 0/1 minterms but missed some don't-care expectations for the minimal SOP/POS reference. B1 fixed `out_pos` and reduced the error count, but final `out_sop` still mismatched don't-care-derived cases.
- Route/debug history shows one accepted edit reducing mismatches, and later bundled don't-care edits rejected because total mismatches increased.
- Likely reason: the repair loop improved the truth table locally but did not infer the full minimal SOP treatment of don't-cares.

## Prob008_m2014_q4h

- Outcome in raw CSV: `routed_only_pass`, but `valid_pair=False`.
- B0 output lacks `properly_finished.tag` and `sim_output.vvp`; logs show internal duplicate-module/reference-module compile issues during the generated-testbench workflow. B1 completed and passed with simple `assign out = in`.
- Likely reason: this is not a clean model-comparison case; the B0 workflow did not complete reliably, so the apparent routed-only win is treated as invalid metadata rather than a measured strict-pair outcome.
