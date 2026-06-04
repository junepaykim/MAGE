# MAGE vs Routed Architecture Budget-Capped Results

## Configuration

- Model: `gpt-5.4-nano`
- Benchmark: `verilog_eval_v2` at `./verilog-eval`
- Final stage: `main_c5`
- Task filter: `^(.*)$`
- Candidate budget: `5`
- Total estimated spend including pilots: `$3.349638`
- Pricing formula: input tokens * $0.20/1M + output tokens * $1.25/1M

## Paper Reference Rows

| System | Model | Benchmark | Setting | Reported Pass@1 |
| --- | --- | --- | --- | ---: |
| Paper MAGE reference | Claude 3.5 Sonnet 2024-10-22 | VerilogEval-Human | High temperature | 94.8 |
| Paper MAGE reference | Claude 3.5 Sonnet 2024-10-22 | VerilogEval-V2 | High temperature | 95.7 |
| Paper MAGE reference | Claude 3.5 Sonnet 2024-10-22 | VerilogEval-Human | Low temperature | 89.1 |
| Paper MAGE reference | Claude 3.5 Sonnet 2024-10-22 | VerilogEval-V2 | Low temperature | 93.6 |

## Measured Results

| System | Model | Tasks completed | Candidate budget | Cost | Pass@1 | Aggregate pass rate | Input tokens | Output tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 MAGE baseline | gpt-5.4-nano | 139 | 5 | $1.333525 | 0.935 | 0.935 | 2212800 | 712765 |
| B1 Proposed routed | gpt-5.4-nano | 139 | 5 | $1.339238 | 0.899 | 0.899 | 2386994 | 689471 |

## Paired Outcomes

| Outcome | Count |
| --- | ---: |
| Both pass | 122 |
| MAGE only passes | 8 |
| Routed only passes | 3 |
| Both fail | 6 |

## Budget

| Bucket | Cost | Projected full V2 cost |
| --- | ---: | ---: |
| Pilot `pilot_c5` | $0.124939 | $4.872621 |
| Final measured stage | $2.672763 | $3.224699 |
| Total | $3.349638 |  |

## B1 Routing

```json
{
  "failed_repairs_by_route": {
    "ambiguous_runnable": 9,
    "interface": 1,
    "logic": 20,
    "syntax": 63
  },
  "failure_class_counts": {
    "ambiguous_runnable": 8,
    "logic": 21,
    "none": 5,
    "syntax": 64
  },
  "route_counts": {
    "ambiguous_runnable": 19,
    "interface": 2,
    "logic": 47,
    "syntax": 86
  },
  "successful_repairs_by_route": {
    "ambiguous_runnable": 1,
    "logic": 4
  }
}
```

## Deliverables

- Paired CSV: `experiment_results/gpt54nano_mage_vs_routed_20260530_152236/main_c5_paired_results.csv`
- B0 output: `/home/joonp/projects/26-sp/ece228/MAGE/output_gpt54nano_v2_b0_mage_t085_n1_main_c5_c5_20260530_152236`
- B1 output: `/home/joonp/projects/26-sp/ece228/MAGE/output_gpt54nano_v2_b1_routed_t085_n1_main_c5_c5_20260530_152236`
- B0 logs: `/home/joonp/projects/26-sp/ece228/MAGE/log_gpt54nano_v2_b0_mage_t085_n1_main_c5_c5_20260530_152236`
- B1 logs: `/home/joonp/projects/26-sp/ece228/MAGE/log_gpt54nano_v2_b1_routed_t085_n1_main_c5_c5_20260530_152236`
- Exact config: `experiment_results/gpt54nano_mage_vs_routed_20260530_152236/exact_runner_config.json`
- Cost report: `experiment_results/gpt54nano_mage_vs_routed_20260530_152236/cost_report.json`
- Validity and raw-cost appendix: `experiment_results/gpt54nano_mage_vs_routed_20260530_152236/validity_and_cost_appendix.md`
- Raw attempted-task CSV: `experiment_results/gpt54nano_mage_vs_routed_20260530_152236/main_c5_raw_attempted_results.csv`
