# Agentic Routing Rerun With Reused Baseline

## Configuration

- Model: `gpt-5.4-nano`
- Benchmark: `verilog_eval_v2` at `./verilog-eval`
- Stage: `agentic_rerun_c5_with_baseline_addons`
- Task filter: `^(.*)$`
- Candidate budget: `5`
- New API spend from B1 rerun only: `$1.554229`
- Stopped by budget: `False`
- Reused baseline output: `/home/joonp/projects/26-sp/ece228/MAGE/output_gpt54nano_v2_b0_mage_t085_n1_main_c5_c5_20260530_152236`
- Baseline add-on output: `/home/joonp/projects/26-sp/ece228/MAGE/output_gpt54nano_v2_b0_mage_t085_n1_baseline_addon_c5_c5_20260603_182054`
- Baseline add-on logs: `/home/joonp/projects/26-sp/ece228/MAGE/log_gpt54nano_v2_b0_mage_t085_n1_baseline_addon_c5_c5_20260603_182054`
- New baseline add-on spend: `$0.108915`
- Merged baseline record: `/home/joonp/projects/26-sp/ece228/MAGE/experiment_results/agentic_routing_rerun_20260603_182054/merged_baseline_record_with_addons.json`

## Measured Results

| System | Source | Tasks completed | Cost in record | Pass@1 | Input tokens | Output tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| B0 MAGE baseline | reused | 148 | $1.451960 | 0.926 | 2417607 | 774743 |
| B1 Proposed routed | new rerun | 148 | $1.395033 | 0.919 | 2514862 | 713642 |

## Paired Outcomes

| Outcome | Count |
| --- | ---: |
| Both pass | 133 |
| Baseline only passes | 4 |
| Agentic routing only passes | 3 |
| Both fail | 8 |

## B1 Routing

```json
{
  "failed_repairs_by_route": {
    "ambiguous_runnable": 21,
    "interface": 3,
    "logic": 27,
    "syntax": 60
  },
  "failure_class_counts": {
    "ambiguous_runnable": 25,
    "interface": 3,
    "logic": 21,
    "none": 5,
    "syntax": 60
  },
  "route_counts": {
    "ambiguous_runnable": 29,
    "interface": 4,
    "logic": 56,
    "syntax": 80
  },
  "successful_repairs_by_route": {
    "logic": 5
  }
}
```

## Debug History Artifacts

- Baseline Prob093 debug history: `/home/joonp/projects/26-sp/ece228/MAGE/output_gpt54nano_v2_b0_mage_t085_n1_main_c5_c5_20260530_152236/VERILOG_EVAL_V2_Prob093_ece241_2014_q3/debug_history.jsonl`
- Agentic Prob093 debug history: `/home/joonp/projects/26-sp/ece228/MAGE/output_gpt54nano_v2_b1_routed_t085_n1_agentic_rerun_c5_c5_20260603_182054/VERILOG_EVAL_V2_Prob093_ece241_2014_q3/debug_history.jsonl`

## Deliverables

- Paired CSV: `/home/joonp/projects/26-sp/ece228/MAGE/experiment_results/agentic_routing_rerun_20260603_182054/agentic_rerun_c5_with_baseline_addons_paired_results.csv`
- Agentic successes with baseline: `/home/joonp/projects/26-sp/ece228/MAGE/experiment_results/agentic_routing_rerun_20260603_182054/agentic_successes_with_baseline.csv`
- Aggregate JSON: `/home/joonp/projects/26-sp/ece228/MAGE/experiment_results/agentic_routing_rerun_20260603_182054/agentic_rerun_c5_with_baseline_addons_aggregate.json`
- B0 output: `/home/joonp/projects/26-sp/ece228/MAGE/output_gpt54nano_v2_b0_mage_t085_n1_main_c5_c5_20260530_152236`
- B1 output: `/home/joonp/projects/26-sp/ece228/MAGE/output_gpt54nano_v2_b1_routed_t085_n1_agentic_rerun_c5_c5_20260603_182054`
- B0 logs: `/home/joonp/projects/26-sp/ece228/MAGE/log_gpt54nano_v2_b0_mage_t085_n1_main_c5_c5_20260530_152236`
- B1 logs: `/home/joonp/projects/26-sp/ece228/MAGE/log_gpt54nano_v2_b1_routed_t085_n1_agentic_rerun_c5_c5_20260603_182054`
