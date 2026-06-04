# Validity And Cost Appendix

This appendix distinguishes raw attempted task outcomes from the strict paired comparison used in `result_summary.md`.

## Accounting

- Main stage attempted paired prefix: `156` tasks.
- Strict valid paired tasks: `139` tasks.
- Invalid workflow-completion pairs: `17` tasks.
- Main-stage all-attempt cost: `$3.224699`.
- Pilot cost: `$0.124939`.
- Total estimated cost: `$3.349638`.
- Raw attempted CSV: `experiment_results/gpt54nano_mage_vs_routed_20260530_152236/main_c5_raw_attempted_results.csv`.

## Raw Attempted Totals

| Arm | Tasks attempted | Raw pass count | Raw pass rate | Cost | Input tokens | Output tokens | Runtime |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 MAGE baseline | 156 | 138 | 0.885 | $1.602971 | 2586990 | 868450 | 1:29:00 |
| B1 routed | 156 | 134 | 0.859 | $1.621728 | 2817768 | 846539 | 1:23:55 |

## Strict Valid-Pair Comparison

| Arm | Valid tasks | Pass count | Pass@1 | Cost on valid tasks | Input tokens | Output tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 MAGE baseline | 139 | 130 | 0.935 | $1.333525 | 2212800 | 712765 |
| B1 routed | 139 | 125 | 0.899 | $1.339238 | 2386994 | 689471 |

## Outcome Counts

| Scope | Both pass | MAGE only | Routed only | Both fail |
| --- | ---: | ---: | ---: | ---: |
| Raw attempted | 129 | 9 | 5 | 13 |
| Strict valid pairs | 122 | 8 | 3 | 6 |

## Invalid Workflow-Completion Pairs

These tasks had at least one arm without `properly_finished.tag`; per the experiment rules they are excluded from the strict paired pass-rate comparison and retained in the raw attempted CSV.

| Task | Raw outcome | B0 pass | B1 pass | Invalid arm(s) | Reason class |
| --- | --- | ---: | ---: | --- | --- |
| Prob002_m2014_q4i | both_pass | True | True | B0 | B0=tb_judge_assertion |
| Prob008_m2014_q4h | routed_only_pass | False | True | B0 | B0=tb_judge_assertion |
| Prob019_m2014_q4f | both_pass | True | True | B0 | B0=tb_judge_assertion |
| Prob021_mux256to1v | both_pass | True | True | B1 | B1=rtl_editor_json_decode |
| Prob031_dff | both_pass | True | True | B0 | B0=tb_judge_assertion |
| Prob093_ece241_2014_q3 | both_fail | False | False | B1 | B1=rtl_editor_json_decode |
| Prob099_m2014_q6c | both_fail | False | False | B0 | B0=tb_judge_assertion |
| Prob100_fsm3comb | both_pass | True | True | B0 | B0=tb_judge_assertion |
| Prob131_mt2015_q4 | routed_only_pass | False | True | B0 | B0=tb_judge_assertion |
| Prob138_2012_q2fsm | both_pass | True | True | B0 | B0=tb_judge_assertion |
| Prob141_count_clock | both_fail | False | False | B0,B1 | B0=tb_generator_json_decode; B1=tb_generator_json_decode |
| Prob143_fsm_onehot | both_pass | True | True | B0 | B0=tb_judge_assertion |
| Prob150_review2015_fsmonehot | both_fail | False | False | B0,B1 | B0=tb_generator_json_decode; B1=tb_generator_json_decode |
| Prob152_lemmings3 | mage_only_pass | True | False | B1 | B1=tb_generator_json_decode |
| Prob153_gshare | both_fail | False | False | B0,B1 | B0=tb_generator_json_decode; B1=tb_generator_json_decode |
| Prob155_lemmings4 | both_fail | False | False | B0,B1 | B0=tb_generator_json_decode; B1=tb_generator_json_decode |
| Prob156_review2015_fancytimer | both_fail | False | False | B0 | B0=tb_judge_assertion |

## Invalid Reason Counts

| Reason class | Count |
| --- | ---: |
| B0=tb_generator_json_decode | 4 |
| B0=tb_judge_assertion | 10 |
| B1=rtl_editor_json_decode | 2 |
| B1=tb_generator_json_decode | 5 |
