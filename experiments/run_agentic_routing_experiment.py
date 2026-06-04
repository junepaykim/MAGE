#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import traceback
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from llama_index.core.llms import LLM

from mage.agent import TopAgent
from mage.benchmark_read_helper import (
    TypeBenchmark,
    TypeBenchmarkFile,
    get_benchmark_contents,
)
from mage.gen_config import get_llm, set_exp_setting
from mage.sim_reviewer import sim_review_golden_benchmark
from mage.token_counter import TokenCount

INPUT_PRICE_PER_TOKEN = 0.20 / 1_000_000
OUTPUT_PRICE_PER_TOKEN = 1.25 / 1_000_000

PILOT_FILTER = (
    r"^(Prob011_norgate|Prob093_ece241_2014_q3|"
    r"Prob119_fsm3|Prob151_review2015_fsm)$"
)
FULL_FILTER = r"^(.*)$"
FALLBACK_FILTER = (
    r"^(Prob011_norgate|Prob023_vector100r|Prob050_kmap1|"
    r"Prob093_ece241_2014_q3|Prob119_fsm3|Prob127_lemmings1|"
    r"Prob151_review2015_fsm|Prob156_review2015_fancytimer)$"
)

PAPER_REFERENCE_ROWS = [
    {
        "system": "Paper MAGE reference",
        "model": "Claude 3.5 Sonnet 2024-10-22",
        "benchmark": "VerilogEval-Human",
        "setting": "High temperature",
        "pass_at_1": "94.8",
    },
    {
        "system": "Paper MAGE reference",
        "model": "Claude 3.5 Sonnet 2024-10-22",
        "benchmark": "VerilogEval-V2",
        "setting": "High temperature",
        "pass_at_1": "95.7",
    },
    {
        "system": "Paper MAGE reference",
        "model": "Claude 3.5 Sonnet 2024-10-22",
        "benchmark": "VerilogEval-Human",
        "setting": "Low temperature",
        "pass_at_1": "89.1",
    },
    {
        "system": "Paper MAGE reference",
        "model": "Claude 3.5 Sonnet 2024-10-22",
        "benchmark": "VerilogEval-V2",
        "setting": "Low temperature",
        "pass_at_1": "93.6",
    },
]


@dataclass(frozen=True)
class ArmConfig:
    key: str
    label: str
    run_identifier: str
    enable_failure_routing: bool


@dataclass
class ExperimentConfig:
    provider: str = "openai"
    model: str = "gpt-5.4-nano"
    type_benchmark: str = "verilog_eval_v2"
    path_benchmark: str = "./verilog-eval"
    temperature: float = 0.85
    top_p: float = 0.95
    n: int = 1
    max_token: int = 4096
    rtl_selected_candidates: int = 1
    editor_max_trials: int = 3
    sim_max_retry: int = 2
    use_golden_tb_in_mage: bool = True
    key_cfg_path: str = "./key.cfg"
    ideal_budget_usd: float = 9.0
    hard_stop_usd: float = 12.0
    candidate_budgets: tuple[int, ...] = (5, 3, 1)
    max_parallel_requests: int = 0


@dataclass
class StageResult:
    name: str
    filter_instance: str
    rtl_max_candidates: int
    output_dirs: dict[str, str]
    log_dirs: dict[str, str]
    reports_dir: str
    tasks_attempted: list[str]
    tasks_valid: list[str]
    total_cost: float
    avg_pair_cost: float
    projected_full_cost: float
    stopped_by_budget: bool
    aggregate: dict[str, Any]


ARMS = [
    ArmConfig(
        key="b0",
        label="B0 MAGE baseline",
        run_identifier="gpt54nano_v2_b0_mage_t085_n1",
        enable_failure_routing=False,
    ),
    ArmConfig(
        key="b1",
        label="B1 Proposed routed",
        run_identifier="gpt54nano_v2_b1_routed_t085_n1",
        enable_failure_routing=True,
    ),
]


def load_secrets() -> None:
    for path in (REPO_ROOT / ".secrets", REPO_ROOT / "key.cfg"):
        if not path.exists():
            continue
        for line in path.read_text(errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export ") :].strip()
            value = value.strip().strip("'").strip('"')
            if key and value and key not in os.environ:
                os.environ[key] = value


def cost_for_tokens(token_count: TokenCount) -> float:
    return (
        token_count.in_token_cnt * INPUT_PRICE_PER_TOKEN
        + token_count.out_token_cnt * OUTPUT_PRICE_PER_TOKEN
    )


def parse_duration(duration: str) -> float:
    try:
        parts = duration.split(":")
        if len(parts) != 3:
            return 0.0
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds
    except ValueError:
        return 0.0


def get_task_specs(config: ExperimentConfig, filter_instance: str) -> dict[str, str]:
    type_benchmark = TypeBenchmark[config.type_benchmark.upper()]
    return get_benchmark_contents(
        type_benchmark,
        TypeBenchmarkFile.SPEC,
        config.path_benchmark,
        filter_instance,
    )


def get_task_paths(
    config: ExperimentConfig, file_type: TypeBenchmarkFile, filter_instance: str
) -> dict[str, str]:
    type_benchmark = TypeBenchmark[config.type_benchmark.upper()]
    return get_benchmark_contents(
        type_benchmark,
        file_type,
        config.path_benchmark,
        filter_instance,
    )


def make_agent(
    llm: LLM,
    arm: ArmConfig,
    config: ExperimentConfig,
    rtl_max_candidates: int,
    output_dir: Path,
    log_dir: Path,
) -> TopAgent:
    agent = TopAgent(llm)
    agent.set_output_path(str(output_dir))
    agent.set_log_path(str(log_dir))
    agent.set_redirect_log(True)
    agent.rtl_max_candidates = rtl_max_candidates
    agent.rtl_selected_candidates = config.rtl_selected_candidates
    agent.editor_max_trials = config.editor_max_trials
    agent.sim_max_retry = config.sim_max_retry
    agent.enable_failure_routing = arm.enable_failure_routing
    if config.max_parallel_requests > 0:
        agent.token_counter.max_parallel_requests = config.max_parallel_requests
    return agent


def empty_record(arm: ArmConfig, config: ExperimentConfig, stage_name: str) -> dict[str, Any]:
    return {
        "metadata": {
            "arm": arm.key,
            "label": arm.label,
            "stage": stage_name,
            "run_identifier": arm.run_identifier,
            "config": asdict(config),
            "cost_formula": {
                "input_price_per_1m_tokens_usd": 0.20,
                "output_price_per_1m_tokens_usd": 1.25,
            },
        },
        "record_per_run": {},
        "total_record": {
            "pass_cnt": 0,
            "total_cnt": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "token_limit_cnt": 0,
            "total_cost": "0.000000",
            "avg_cost": "0.000000",
            "total_run_time": "0:00:00",
        },
    }


def update_total_record(record: dict[str, Any]) -> None:
    rows = record["record_per_run"]
    pass_cnt = sum(1 for row in rows.values() if row.get("is_pass"))
    input_tokens = sum(int(row.get("input_tokens", 0)) for row in rows.values())
    output_tokens = sum(int(row.get("output_tokens", 0)) for row in rows.values())
    token_limit_cnt = sum(int(row.get("run_token_limit_cnt", 0)) for row in rows.values())
    total_cost = sum(float(row.get("estimated_cost", 0.0)) for row in rows.values())
    total_runtime_seconds = sum(
        parse_duration(str(row.get("run_time", "0:00:00"))) for row in rows.values()
    )
    total_cnt = len(rows)
    record["total_record"] = {
        "pass_cnt": pass_cnt,
        "total_cnt": total_cnt,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "token_limit_cnt": token_limit_cnt,
        "total_cost": f"{total_cost:.6f}",
        "avg_cost": f"{(total_cost / total_cnt) if total_cnt else 0.0:.6f}",
        "total_run_time": str(timedelta(seconds=round(total_runtime_seconds))),
    }


def write_record(output_root: Path, record: dict[str, Any]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    update_total_record(record)
    (output_root / "record.json").write_text(json.dumps(record, indent=2))


def run_one_task(
    *,
    agent: TopAgent,
    arm: ArmConfig,
    config: ExperimentConfig,
    task_id: str,
    spec: str,
    golden_tb_path: str | None,
    golden_rtl_path: str | None,
) -> dict[str, Any]:
    type_benchmark = TypeBenchmark[config.type_benchmark.upper()]
    start_time = time.monotonic()
    crash = ""
    golden_sim_log = ""
    is_pass = False
    try:
        agent.run(
            benchmark_type_name=type_benchmark.name,
            task_id=task_id,
            spec=spec,
            golden_tb_path=golden_tb_path,
            golden_rtl_blackbox_path=golden_rtl_path,
        )
        try:
            is_pass, golden_sim_log = sim_review_golden_benchmark(
                task_id=task_id,
                output_path=agent.output_path,
                benchmark_type=type_benchmark,
                benchmark_path=config.path_benchmark,
            )
        except Exception:
            crash = traceback.format_exc(limit=3)
            is_pass = False
    except Exception:
        crash = traceback.format_exc(limit=5)
        is_pass = False
    run_time = timedelta(seconds=time.monotonic() - start_time)
    token_count = agent.token_counter.get_sum_count()
    estimated_cost = cost_for_tokens(token_count)
    output_dir = (
        Path(agent.output_path)
        / f"{type_benchmark.name}_{task_id}"
    )
    properly_finished = output_dir.joinpath("properly_finished.tag").exists()
    return {
        "arm": arm.key,
        "task_id": task_id,
        "is_pass": is_pass,
        "properly_finished": properly_finished,
        "crash": crash,
        "input_tokens": token_count.in_token_cnt,
        "output_tokens": token_count.out_token_cnt,
        "run_token_limit_cnt": agent.token_counter.get_total_token(),
        "estimated_cost": f"{estimated_cost:.6f}",
        "run_time": str(run_time),
        "golden_sim_log_excerpt": golden_sim_log[:2000],
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def route_stats_for_task(output_root: Path, task_id: str) -> dict[str, Any]:
    task_dir = output_root / f"VERILOG_EVAL_V2_{task_id}"
    route_rows = read_jsonl(task_dir / "route_history.jsonl")
    debug_rows = read_jsonl(task_dir / "debug_history.jsonl")
    route_counts = Counter(row.get("repair_route") for row in route_rows)
    route_counts.update(row.get("repair_route_before") for row in debug_rows)
    route_counts.pop(None, None)
    repair_success = Counter(
        row.get("repair_route_before")
        for row in debug_rows
        if row.get("is_sim_pass")
    )
    repair_fail = Counter(
        row.get("repair_route_before")
        for row in debug_rows
        if not row.get("is_sim_pass")
    )
    failure_class_counts = Counter(row.get("failure_class") for row in debug_rows)
    failure_class_counts.pop(None, None)
    return {
        "route_counts": dict(route_counts),
        "successful_repairs_by_route": dict(repair_success),
        "failed_repairs_by_route": dict(repair_fail),
        "failure_class_counts": dict(failure_class_counts),
        "debug_attempts": len(debug_rows),
    }


def aggregate_stage(
    *,
    stage_name: str,
    reports_dir: Path,
    arm_records: dict[str, dict[str, Any]],
    output_dirs: dict[str, Path],
    log_dirs: dict[str, Path],
    filter_instance: str,
    rtl_max_candidates: int,
) -> dict[str, Any]:
    b0_rows = arm_records["b0"]["record_per_run"]
    b1_rows = arm_records["b1"]["record_per_run"]
    task_ids = [task_id for task_id in b0_rows if task_id in b1_rows]
    invalid_tasks = []
    paired_rows = []
    outcome_counts = Counter()
    arm_stats: dict[str, dict[str, Any]] = {}

    for task_id in task_ids:
        b0 = b0_rows[task_id]
        b1 = b1_rows[task_id]
        valid = bool(b0.get("properly_finished")) and bool(b1.get("properly_finished"))
        if not valid:
            invalid_tasks.append(task_id)
        b0_pass = bool(b0.get("is_pass"))
        b1_pass = bool(b1.get("is_pass"))
        if b0_pass and b1_pass:
            outcome = "both_pass"
        elif b0_pass:
            outcome = "mage_only_pass"
        elif b1_pass:
            outcome = "routed_only_pass"
        else:
            outcome = "both_fail"
        if valid:
            outcome_counts[outcome] += 1
        route_stats = route_stats_for_task(output_dirs["b1"], task_id)
        paired_rows.append(
            {
                "task_id": task_id,
                "valid_pair": valid,
                "b0_pass": b0_pass,
                "b1_pass": b1_pass,
                "outcome": outcome,
                "b0_input_tokens": b0.get("input_tokens", 0),
                "b0_output_tokens": b0.get("output_tokens", 0),
                "b0_cost": b0.get("estimated_cost", "0.000000"),
                "b0_runtime": b0.get("run_time", ""),
                "b1_input_tokens": b1.get("input_tokens", 0),
                "b1_output_tokens": b1.get("output_tokens", 0),
                "b1_cost": b1.get("estimated_cost", "0.000000"),
                "b1_runtime": b1.get("run_time", ""),
                "b1_route_counts": json.dumps(route_stats["route_counts"], sort_keys=True),
                "b1_successful_repairs_by_route": json.dumps(
                    route_stats["successful_repairs_by_route"], sort_keys=True
                ),
                "b1_failed_repairs_by_route": json.dumps(
                    route_stats["failed_repairs_by_route"], sort_keys=True
                ),
            }
        )

    valid_task_ids = [row["task_id"] for row in paired_rows if row["valid_pair"]]
    for arm in ARMS:
        rows = arm_records[arm.key]["record_per_run"]
        valid_rows = [rows[task_id] for task_id in valid_task_ids]
        pass_cnt = sum(1 for row in valid_rows if row.get("is_pass"))
        total_cost = sum(float(row.get("estimated_cost", 0.0)) for row in valid_rows)
        input_tokens = sum(int(row.get("input_tokens", 0)) for row in valid_rows)
        output_tokens = sum(int(row.get("output_tokens", 0)) for row in valid_rows)
        arm_stats[arm.key] = {
            "label": arm.label,
            "run_identifier": arm.run_identifier,
            "tasks_completed": len(valid_rows),
            "pass_count": pass_cnt,
            "aggregate_pass_rate": pass_cnt / len(valid_rows) if valid_rows else 0.0,
            "pass_at_1": pass_cnt / len(valid_rows) if valid_rows else 0.0,
            "compile_success_rate": sum(
                1 for row in valid_rows if row.get("properly_finished")
            )
            / len(valid_rows)
            if valid_rows
            else 0.0,
            "simulation_success_rate": pass_cnt / len(valid_rows) if valid_rows else 0.0,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost": total_cost,
            "runtime_seconds": sum(
                parse_duration(str(row.get("run_time", "0:00:00")))
                for row in valid_rows
            ),
            "output_path": str(output_dirs[arm.key]),
            "log_path": str(log_dirs[arm.key]),
        }

    route_totals: dict[str, Counter] = defaultdict(Counter)
    for task_id in valid_task_ids:
        stats = route_stats_for_task(output_dirs["b1"], task_id)
        for key in (
            "route_counts",
            "successful_repairs_by_route",
            "failed_repairs_by_route",
            "failure_class_counts",
        ):
            route_totals[key].update(stats[key])

    reports_dir.mkdir(parents=True, exist_ok=True)
    paired_csv = reports_dir / f"{stage_name}_paired_results.csv"
    with paired_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(paired_rows[0].keys()) if paired_rows else ["task_id"])
        writer.writeheader()
        writer.writerows(paired_rows)

    aggregate = {
        "stage": stage_name,
        "filter_instance": filter_instance,
        "rtl_max_candidates": rtl_max_candidates,
        "task_ids": task_ids,
        "valid_task_ids": valid_task_ids,
        "invalid_tasks": invalid_tasks,
        "arm_stats": arm_stats,
        "paired_outcome_counts": dict(outcome_counts),
        "b1_route_totals": {key: dict(value) for key, value in route_totals.items()},
        "paired_csv": str(paired_csv),
    }
    (reports_dir / f"{stage_name}_aggregate.json").write_text(
        json.dumps(aggregate, indent=2)
    )
    return aggregate


def write_markdown_summary(
    *,
    reports_dir: Path,
    stage_result: StageResult,
    total_spend: float,
    pilot_results: list[StageResult],
    config: ExperimentConfig,
) -> Path:
    aggregate = stage_result.aggregate
    arm_stats = aggregate["arm_stats"]
    outcomes = aggregate["paired_outcome_counts"]
    route_totals = aggregate["b1_route_totals"]
    summary_path = reports_dir / "result_summary.md"
    lines = [
        "# MAGE vs Routed Architecture Budget-Capped Results",
        "",
        "## Configuration",
        "",
        f"- Model: `{config.model}`",
        f"- Benchmark: `{config.type_benchmark}` at `{config.path_benchmark}`",
        f"- Final stage: `{stage_result.name}`",
        f"- Task filter: `{stage_result.filter_instance}`",
        f"- Candidate budget: `{stage_result.rtl_max_candidates}`",
        f"- Total estimated spend including pilots: `${total_spend:.6f}`",
        f"- Pricing formula: input tokens * $0.20/1M + output tokens * $1.25/1M",
        "",
        "## Paper Reference Rows",
        "",
        "| System | Model | Benchmark | Setting | Reported Pass@1 |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for row in PAPER_REFERENCE_ROWS:
        lines.append(
            f"| {row['system']} | {row['model']} | {row['benchmark']} | "
            f"{row['setting']} | {row['pass_at_1']} |"
        )
    lines.extend(
        [
            "",
            "## Measured Results",
            "",
            "| System | Model | Tasks completed | Candidate budget | Cost | Pass@1 | Aggregate pass rate | Input tokens | Output tokens |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for arm_key in ("b0", "b1"):
        stats = arm_stats[arm_key]
        lines.append(
            f"| {stats['label']} | {config.model} | {stats['tasks_completed']} | "
            f"{stage_result.rtl_max_candidates} | ${stats['estimated_cost']:.6f} | "
            f"{stats['pass_at_1']:.3f} | {stats['aggregate_pass_rate']:.3f} | "
            f"{stats['input_tokens']} | {stats['output_tokens']} |"
        )
    lines.extend(
        [
            "",
            "## Paired Outcomes",
            "",
            "| Outcome | Count |",
            "| --- | ---: |",
            f"| Both pass | {outcomes.get('both_pass', 0)} |",
            f"| MAGE only passes | {outcomes.get('mage_only_pass', 0)} |",
            f"| Routed only passes | {outcomes.get('routed_only_pass', 0)} |",
            f"| Both fail | {outcomes.get('both_fail', 0)} |",
            "",
            "## Budget",
            "",
            "| Bucket | Cost | Projected full V2 cost |",
            "| --- | ---: | ---: |",
        ]
    )
    for result in pilot_results:
        lines.append(
            f"| Pilot `{result.name}` | ${result.total_cost:.6f} | "
            f"${result.projected_full_cost:.6f} |"
        )
    final_arm_cost = sum(
        stats["estimated_cost"] for stats in arm_stats.values()
    )
    lines.extend(
        [
            f"| Final measured stage | ${final_arm_cost:.6f} | ${stage_result.projected_full_cost:.6f} |",
            f"| Total | ${total_spend:.6f} |  |",
            "",
            "## B1 Routing",
            "",
            "```json",
            json.dumps(route_totals, indent=2, sort_keys=True),
            "```",
            "",
            "## Deliverables",
            "",
            f"- Paired CSV: `{aggregate['paired_csv']}`",
            f"- B0 output: `{stage_result.output_dirs['b0']}`",
            f"- B1 output: `{stage_result.output_dirs['b1']}`",
            f"- B0 logs: `{stage_result.log_dirs['b0']}`",
            f"- B1 logs: `{stage_result.log_dirs['b1']}`",
            f"- Exact config: `{reports_dir / 'exact_runner_config.json'}`",
            f"- Cost report: `{reports_dir / 'cost_report.json'}`",
        ]
    )
    summary_path.write_text("\n".join(lines) + "\n")
    return summary_path


def write_failure_analysis(reports_dir: Path, aggregate: dict[str, Any]) -> Path:
    paired_csv = Path(aggregate["paired_csv"])
    rows = []
    with paired_csv.open() as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    selected = []
    wanted = ["routed_only_pass", "mage_only_pass", "both_fail", "both_pass"]
    for outcome in wanted:
        for row in rows:
            if row.get("valid_pair") == "True" and row.get("outcome") == outcome:
                selected.append(row)
                break
    analysis_path = reports_dir / "representative_failure_analysis.md"
    lines = ["# Representative Failure Analysis", ""]
    if not selected:
        lines.append("No valid paired cases were available for case-study analysis.")
    for row in selected[:5]:
        b0_cost = float(row.get("b0_cost", 0.0))
        b1_cost = float(row.get("b1_cost", 0.0))
        lines.extend(
            [
                f"## {row['task_id']}",
                "",
                f"- Outcome: `{row['outcome']}`",
                f"- B0 pass: `{row['b0_pass']}`; B1 pass: `{row['b1_pass']}`",
                f"- Cost delta B1-B0: `${b1_cost - b0_cost:.6f}`",
                f"- B1 route counts: `{row.get('b1_route_counts', '{}')}`",
                f"- Evidence: final pass/fail comes from the golden VerilogEval testbench. "
                "Route impact is inferred from the B1 route/debug history, not from waveform inspection.",
                "",
            ]
        )
    analysis_path.write_text("\n".join(lines))
    return analysis_path


def resolve_repo_path(path: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    return candidate


def load_record(output_dir: Path) -> dict[str, Any]:
    record_path = output_dir / "record.json"
    if not record_path.exists():
        raise FileNotFoundError(f"Missing record.json at {record_path}")
    return json.loads(record_path.read_text())


def infer_log_dir_from_output(output_dir: Path) -> Path:
    name = output_dir.name
    if name.startswith("output_"):
        return output_dir.with_name(f"log_{name[len('output_') :]}")
    return output_dir.with_name(f"log_{name}")


def run_single_arm_stage(
    *,
    name: str,
    arm: ArmConfig,
    config: ExperimentConfig,
    llm: LLM,
    filter_instance: str,
    rtl_max_candidates: int,
    total_spend_before: float,
    next_task_estimate: float | None,
    hard_stop_enabled: bool,
    artifact_suffix: str = "",
) -> tuple[dict[str, Any], Path, Path, list[str], float, bool]:
    specs = get_task_specs(config, filter_instance)
    golden_tb_paths = get_task_paths(config, TypeBenchmarkFile.TEST_PATH, filter_instance)
    golden_rtl_paths = get_task_paths(config, TypeBenchmarkFile.GOLDEN_PATH, filter_instance)
    run_id = f"{arm.run_identifier}_{name}_c{rtl_max_candidates}"
    if artifact_suffix:
        run_id = f"{run_id}_{artifact_suffix}"
    output_dir = REPO_ROOT / f"output_{run_id}"
    log_dir = REPO_ROOT / f"log_{run_id}"
    record = empty_record(arm, config, name)
    agent = make_agent(llm, arm, config, rtl_max_candidates, output_dir, log_dir)
    write_record(output_dir, record)

    task_costs: list[float] = []
    tasks_attempted: list[str] = []
    stopped_by_budget = False
    stage_spend = 0.0
    for task_id, spec in specs.items():
        observed_task_estimate = (
            max(sum(task_costs) / len(task_costs), next_task_estimate or 0.0)
            if task_costs
            else (next_task_estimate or 0.0)
        )
        if (
            hard_stop_enabled
            and observed_task_estimate
            and total_spend_before + stage_spend + observed_task_estimate
            > config.hard_stop_usd
        ):
            stopped_by_budget = True
            break
        print(f"[{name}:{arm.key}] task {len(tasks_attempted) + 1}/{len(specs)}: {task_id}", flush=True)
        row = run_one_task(
            agent=agent,
            arm=arm,
            config=config,
            task_id=task_id,
            spec=spec,
            golden_tb_path=(
                golden_tb_paths[task_id] if config.use_golden_tb_in_mage else None
            ),
            golden_rtl_path=(
                golden_rtl_paths[task_id] if config.use_golden_tb_in_mage else None
            ),
        )
        record["record_per_run"][task_id] = row
        write_record(output_dir, record)
        task_cost = float(row["estimated_cost"])
        task_costs.append(task_cost)
        stage_spend += task_cost
        tasks_attempted.append(task_id)
    return record, output_dir, log_dir, tasks_attempted, stage_spend, stopped_by_budget


def write_agentic_only_summary(
    *,
    reports_dir: Path,
    aggregate: dict[str, Any],
    config: ExperimentConfig,
    baseline_output_dir: Path,
    baseline_log_dir: Path,
    agentic_output_dir: Path,
    agentic_log_dir: Path,
    new_agentic_spend: float,
    stopped_by_budget: bool,
) -> Path:
    arm_stats = aggregate["arm_stats"]
    outcomes = aggregate["paired_outcome_counts"]
    route_totals = aggregate["b1_route_totals"]
    summary_path = reports_dir / "agentic_rerun_summary.md"
    prob093_baseline = (
        baseline_output_dir
        / "VERILOG_EVAL_V2_Prob093_ece241_2014_q3"
        / "debug_history.jsonl"
    )
    prob093_agentic = (
        agentic_output_dir
        / "VERILOG_EVAL_V2_Prob093_ece241_2014_q3"
        / "debug_history.jsonl"
    )
    aggregate_json = reports_dir / f"{aggregate['stage']}_aggregate.json"
    lines = [
        "# Agentic Routing Rerun With Reused Baseline",
        "",
        "## Configuration",
        "",
        f"- Model: `{config.model}`",
        f"- Benchmark: `{config.type_benchmark}` at `{config.path_benchmark}`",
        f"- Stage: `{aggregate['stage']}`",
        f"- Task filter: `{aggregate['filter_instance']}`",
        f"- Candidate budget: `{aggregate['rtl_max_candidates']}`",
        f"- New API spend from B1 rerun only: `${new_agentic_spend:.6f}`",
        f"- Stopped by budget: `{stopped_by_budget}`",
        f"- Reused baseline output: `{baseline_output_dir}`",
        "",
        "## Measured Results",
        "",
        "| System | Source | Tasks completed | Cost in record | Pass@1 | Input tokens | Output tokens |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    lines.append(
        f"| {arm_stats['b0']['label']} | reused | {arm_stats['b0']['tasks_completed']} | "
        f"${arm_stats['b0']['estimated_cost']:.6f} | {arm_stats['b0']['pass_at_1']:.3f} | "
        f"{arm_stats['b0']['input_tokens']} | {arm_stats['b0']['output_tokens']} |"
    )
    lines.append(
        f"| {arm_stats['b1']['label']} | new rerun | {arm_stats['b1']['tasks_completed']} | "
        f"${arm_stats['b1']['estimated_cost']:.6f} | {arm_stats['b1']['pass_at_1']:.3f} | "
        f"{arm_stats['b1']['input_tokens']} | {arm_stats['b1']['output_tokens']} |"
    )
    lines.extend(
        [
            "",
            "## Paired Outcomes",
            "",
            "| Outcome | Count |",
            "| --- | ---: |",
            f"| Both pass | {outcomes.get('both_pass', 0)} |",
            f"| Baseline only passes | {outcomes.get('mage_only_pass', 0)} |",
            f"| Agentic routing only passes | {outcomes.get('routed_only_pass', 0)} |",
            f"| Both fail | {outcomes.get('both_fail', 0)} |",
            "",
            "## B1 Routing",
            "",
            "```json",
            json.dumps(route_totals, indent=2, sort_keys=True),
            "```",
            "",
            "## Debug History Artifacts",
            "",
            f"- Baseline Prob093 debug history: `{prob093_baseline}`",
            f"- Agentic Prob093 debug history: `{prob093_agentic}`",
            "",
            "## Deliverables",
            "",
            f"- Paired CSV: `{aggregate['paired_csv']}`",
            f"- Agentic successes with baseline: `{reports_dir / 'agentic_successes_with_baseline.csv'}`",
            f"- Aggregate JSON: `{aggregate_json}`",
            f"- B0 output: `{baseline_output_dir}`",
            f"- B1 output: `{agentic_output_dir}`",
            f"- B0 logs: `{baseline_log_dir}`",
            f"- B1 logs: `{agentic_log_dir}`",
        ]
    )
    summary_path.write_text("\n".join(lines) + "\n")
    return summary_path


def write_agentic_successes_csv(reports_dir: Path, paired_csv: Path) -> Path:
    output_path = reports_dir / "agentic_successes_with_baseline.csv"
    with paired_csv.open() as f:
        rows = [row for row in csv.DictReader(f) if row.get("b1_pass") == "True"]
    if rows:
        fieldnames = list(rows[0].keys())
    else:
        fieldnames = ["task_id"]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def run_stage(
    *,
    name: str,
    config: ExperimentConfig,
    llm: LLM,
    filter_instance: str,
    rtl_max_candidates: int,
    reports_dir: Path,
    total_spend_before: float,
    next_pair_estimate: float | None,
    hard_stop_enabled: bool,
    artifact_suffix: str = "",
) -> StageResult:
    specs = get_task_specs(config, filter_instance)
    golden_tb_paths = get_task_paths(config, TypeBenchmarkFile.TEST_PATH, filter_instance)
    golden_rtl_paths = get_task_paths(config, TypeBenchmarkFile.GOLDEN_PATH, filter_instance)
    stage_records: dict[str, dict[str, Any]] = {}
    output_dirs: dict[str, Path] = {}
    log_dirs: dict[str, Path] = {}
    agents: dict[str, TopAgent] = {}
    for arm in ARMS:
        run_id = f"{arm.run_identifier}_{name}_c{rtl_max_candidates}"
        if artifact_suffix:
            run_id = f"{run_id}_{artifact_suffix}"
        output_dir = REPO_ROOT / f"output_{run_id}"
        log_dir = REPO_ROOT / f"log_{run_id}"
        output_dirs[arm.key] = output_dir
        log_dirs[arm.key] = log_dir
        stage_records[arm.key] = empty_record(arm, config, name)
        agents[arm.key] = make_agent(
            llm, arm, config, rtl_max_candidates, output_dir, log_dir
        )
        write_record(output_dir, stage_records[arm.key])

    pair_costs: list[float] = []
    tasks_attempted: list[str] = []
    stopped_by_budget = False
    stage_spend = 0.0
    for task_id, spec in specs.items():
        observed_pair_estimate = (
            max(sum(pair_costs) / len(pair_costs), next_pair_estimate or 0.0)
            if pair_costs
            else (next_pair_estimate or 0.0)
        )
        if (
            hard_stop_enabled
            and observed_pair_estimate
            and total_spend_before + stage_spend + observed_pair_estimate
            > config.hard_stop_usd
        ):
            stopped_by_budget = True
            break
        print(f"[{name}] task {len(tasks_attempted) + 1}/{len(specs)}: {task_id}", flush=True)
        pair_cost = 0.0
        for arm in ARMS:
            row = run_one_task(
                agent=agents[arm.key],
                arm=arm,
                config=config,
                task_id=task_id,
                spec=spec,
                golden_tb_path=(
                    golden_tb_paths[task_id] if config.use_golden_tb_in_mage else None
                ),
                golden_rtl_path=(
                    golden_rtl_paths[task_id] if config.use_golden_tb_in_mage else None
                ),
            )
            stage_records[arm.key]["record_per_run"][task_id] = row
            write_record(output_dirs[arm.key], stage_records[arm.key])
            pair_cost += float(row["estimated_cost"])
        pair_costs.append(pair_cost)
        stage_spend += pair_cost
        tasks_attempted.append(task_id)

    aggregate = aggregate_stage(
        stage_name=name,
        reports_dir=reports_dir,
        arm_records=stage_records,
        output_dirs=output_dirs,
        log_dirs=log_dirs,
        filter_instance=filter_instance,
        rtl_max_candidates=rtl_max_candidates,
    )
    avg_pair_cost = sum(pair_costs) / len(pair_costs) if pair_costs else 0.0
    projected_full_cost = avg_pair_cost * 156
    return StageResult(
        name=name,
        filter_instance=filter_instance,
        rtl_max_candidates=rtl_max_candidates,
        output_dirs={key: str(value) for key, value in output_dirs.items()},
        log_dirs={key: str(value) for key, value in log_dirs.items()},
        reports_dir=str(reports_dir),
        tasks_attempted=tasks_attempted,
        tasks_valid=aggregate["valid_task_ids"],
        total_cost=stage_spend,
        avg_pair_cost=avg_pair_cost,
        projected_full_cost=projected_full_cost,
        stopped_by_budget=stopped_by_budget,
        aggregate=aggregate,
    )


def choose_main_plan(
    pilot_result: StageResult,
    config: ExperimentConfig,
) -> tuple[str, str, bool]:
    projected = pilot_result.projected_full_cost
    if projected <= config.ideal_budget_usd:
        return "full", FULL_FILTER, True
    if projected <= config.hard_stop_usd:
        return "full", FULL_FILTER, True
    return "reduce", "", False


def sanitize_artifact_suffix(suffix: str) -> str:
    suffix = suffix.strip()
    if not suffix:
        return ""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", suffix).strip("_")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reports-dir", default="")
    parser.add_argument(
        "--artifact-suffix",
        default="",
        help=(
            "Optional suffix appended to raw output/log directories so repeated "
            "runs do not reuse prior artifacts."
        ),
    )
    parser.add_argument("--skip-main", action="store_true")
    parser.add_argument("--force-filter", default="")
    parser.add_argument("--force-candidates", type=int, default=0)
    parser.add_argument(
        "--agentic-only",
        action="store_true",
        help="Run only the routed B1 arm and aggregate it with a reused B0 record.",
    )
    parser.add_argument(
        "--baseline-output-dir",
        default="",
        help="Existing B0 output directory containing record.json for --agentic-only.",
    )
    parser.add_argument(
        "--baseline-log-dir",
        default="",
        help="Existing B0 log directory. If omitted, inferred from baseline output name.",
    )
    parser.add_argument(
        "--max-parallel-requests",
        type=int,
        default=0,
        help="Override TokenCounter max_parallel_requests for batched LLM calls.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    os.chdir(REPO_ROOT)
    load_secrets()
    config = ExperimentConfig()
    if args.max_parallel_requests > 0:
        config.max_parallel_requests = args.max_parallel_requests
    set_exp_setting(temperature=config.temperature, top_p=config.top_p)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    artifact_suffix = sanitize_artifact_suffix(args.artifact_suffix)
    reports_dir = (
        Path(args.reports_dir)
        if args.reports_dir
        else REPO_ROOT / "experiment_results" / f"gpt54nano_mage_vs_routed_{stamp}"
    )
    reports_dir.mkdir(parents=True, exist_ok=True)
    exact_runner_config = asdict(config)
    exact_runner_config["artifact_suffix"] = artifact_suffix
    exact_runner_config["reports_dir"] = str(reports_dir)
    (reports_dir / "exact_runner_config.json").write_text(
        json.dumps(exact_runner_config, indent=2)
    )
    print("Verifying model access with configured OpenAI credentials.", flush=True)
    llm = get_llm(
        model=config.model,
        cfg_path=config.key_cfg_path,
        max_token=config.max_token,
        provider=config.provider,
    )

    if args.agentic_only:
        if not args.baseline_output_dir:
            raise ValueError("--agentic-only requires --baseline-output-dir")
        chosen_candidates = args.force_candidates or config.candidate_budgets[0]
        final_filter = args.force_filter or FULL_FILTER
        baseline_output_dir = resolve_repo_path(args.baseline_output_dir)
        baseline_log_dir = (
            resolve_repo_path(args.baseline_log_dir)
            if args.baseline_log_dir
            else infer_log_dir_from_output(baseline_output_dir)
        )
        baseline_record = load_record(baseline_output_dir)
        b1_record, b1_output_dir, b1_log_dir, tasks_attempted, b1_spend, stopped = (
            run_single_arm_stage(
                name=f"agentic_rerun_c{chosen_candidates}",
                arm=ARMS[1],
                config=config,
                llm=llm,
                filter_instance=final_filter,
                rtl_max_candidates=chosen_candidates,
                total_spend_before=0.0,
                next_task_estimate=None,
                hard_stop_enabled=True,
                artifact_suffix=artifact_suffix,
            )
        )
        aggregate = aggregate_stage(
            stage_name=f"agentic_rerun_c{chosen_candidates}",
            reports_dir=reports_dir,
            arm_records={"b0": baseline_record, "b1": b1_record},
            output_dirs={"b0": baseline_output_dir, "b1": b1_output_dir},
            log_dirs={"b0": baseline_log_dir, "b1": b1_log_dir},
            filter_instance=final_filter,
            rtl_max_candidates=chosen_candidates,
        )
        success_csv = write_agentic_successes_csv(
            reports_dir, Path(aggregate["paired_csv"])
        )
        cost_report = {
            "mode": "agentic_only_reused_baseline",
            "new_agentic_estimated_cost": b1_spend,
            "tasks_attempted": tasks_attempted,
            "stopped_by_budget": stopped,
            "baseline_output_dir": str(baseline_output_dir),
            "baseline_log_dir": str(baseline_log_dir),
            "agentic_output_dir": str(b1_output_dir),
            "agentic_log_dir": str(b1_log_dir),
            "success_csv": str(success_csv),
            "aggregate": aggregate,
            "hard_stop_usd": config.hard_stop_usd,
        }
        (reports_dir / "cost_report.json").write_text(json.dumps(cost_report, indent=2))
        summary_path = write_agentic_only_summary(
            reports_dir=reports_dir,
            aggregate=aggregate,
            config=config,
            baseline_output_dir=baseline_output_dir,
            baseline_log_dir=baseline_log_dir,
            agentic_output_dir=b1_output_dir,
            agentic_log_dir=b1_log_dir,
            new_agentic_spend=b1_spend,
            stopped_by_budget=stopped,
        )
        failure_analysis_path = write_failure_analysis(reports_dir, aggregate)
        print(f"Summary: {summary_path}", flush=True)
        print(f"Failure analysis: {failure_analysis_path}", flush=True)
        print(f"New B1 estimated cost: ${b1_spend:.6f}", flush=True)
        return

    total_spend = 0.0
    pilot_results: list[StageResult] = []
    chosen_candidates = args.force_candidates or 0
    final_filter = args.force_filter or ""
    hard_stop_enabled = False
    if not final_filter:
        for candidate_budget in config.candidate_budgets:
            pilot = run_stage(
                name=f"pilot_c{candidate_budget}",
                config=config,
                llm=llm,
                filter_instance=PILOT_FILTER,
                rtl_max_candidates=candidate_budget,
                reports_dir=reports_dir,
                total_spend_before=total_spend,
                next_pair_estimate=None,
                hard_stop_enabled=False,
                artifact_suffix=artifact_suffix,
            )
            pilot_results.append(pilot)
            total_spend += pilot.total_cost
            action, filter_instance, hard_stop = choose_main_plan(pilot, config)
            if action != "reduce":
                chosen_candidates = candidate_budget
                final_filter = filter_instance
                hard_stop_enabled = hard_stop
                break
        if not final_filter:
            chosen_candidates = config.candidate_budgets[-1]
            final_filter = FALLBACK_FILTER
            hard_stop_enabled = True
    else:
        chosen_candidates = chosen_candidates or config.candidate_budgets[0]
        hard_stop_enabled = True

    if args.skip_main:
        final_stage = pilot_results[-1]
    else:
        next_pair_estimate = (
            max(pilot.avg_pair_cost for pilot in pilot_results)
            if pilot_results
            else None
        )
        final_stage = run_stage(
            name=f"main_c{chosen_candidates}",
            config=config,
            llm=llm,
            filter_instance=final_filter,
            rtl_max_candidates=chosen_candidates,
            reports_dir=reports_dir,
            total_spend_before=total_spend,
            next_pair_estimate=next_pair_estimate,
            hard_stop_enabled=hard_stop_enabled,
            artifact_suffix=artifact_suffix,
        )
        total_spend += final_stage.total_cost

    cost_report = {
        "total_estimated_cost": total_spend,
        "pilot_results": [asdict(result) for result in pilot_results],
        "final_stage": asdict(final_stage),
        "hard_stop_usd": config.hard_stop_usd,
    }
    (reports_dir / "cost_report.json").write_text(json.dumps(cost_report, indent=2))
    summary_path = write_markdown_summary(
        reports_dir=reports_dir,
        stage_result=final_stage,
        total_spend=total_spend,
        pilot_results=pilot_results,
        config=config,
    )
    failure_analysis_path = write_failure_analysis(reports_dir, final_stage.aggregate)
    print(f"Summary: {summary_path}", flush=True)
    print(f"Failure analysis: {failure_analysis_path}", flush=True)
    print(f"Total estimated cost: ${total_spend:.6f}", flush=True)


if __name__ == "__main__":
    main()
