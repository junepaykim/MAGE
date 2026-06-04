# Representative Failure Analysis

## Prob037_review2015_count1k

- Outcome: `routed_only_pass`
- B0 pass: `False`; B1 pass: `True`
- Cost delta B1-B0: `$-0.001877`
- B1 route counts: `{"ambiguous_runnable": 4}`
- Evidence: final pass/fail comes from the golden VerilogEval testbench. Route impact is inferred from the B1 route/debug history, not from waveform inspection.

## Prob062_bugs_mux2

- Outcome: `mage_only_pass`
- B0 pass: `True`; B1 pass: `False`
- Cost delta B1-B0: `$0.002617`
- B1 route counts: `{"interface": 4}`
- Evidence: final pass/fail comes from the golden VerilogEval testbench. Route impact is inferred from the B1 route/debug history, not from waveform inspection.

## Prob070_ece241_2013_q2

- Outcome: `both_fail`
- B0 pass: `False`; B1 pass: `False`
- Cost delta B1-B0: `$0.000116`
- B1 route counts: `{"logic": 4}`
- Evidence: final pass/fail comes from the golden VerilogEval testbench. Route impact is inferred from the B1 route/debug history, not from waveform inspection.

## Prob001_zero

- Outcome: `both_pass`
- B0 pass: `True`; B1 pass: `True`
- Cost delta B1-B0: `$0.000060`
- B1 route counts: `{}`
- Evidence: final pass/fail comes from the golden VerilogEval testbench. Route impact is inferred from the B1 route/debug history, not from waveform inspection.
