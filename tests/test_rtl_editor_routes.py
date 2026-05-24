import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from llama_index.core.base.llms.types import ChatMessage, ChatResponse, MessageRole

from mage.rtl_editor import (
    RTLEditor,
    classify_debug_failure,
    normalize_repair_route,
)
from mage.sim_judge import SimJudge
from mage.sim_reviewer import sim_review_mismatch_cnt


def command_output(stdout: str = "", stderr: str = "") -> str:
    return json.dumps({"stdout": stdout, "stderr": stderr})


class FakeSimReviewer:
    def __init__(self, is_pass: bool, mismatch_cnt: int, sim_output: str):
        self.is_pass = is_pass
        self.mismatch_cnt = mismatch_cnt
        self.sim_output = sim_output

    def review(self):
        return self.is_pass, self.mismatch_cnt, self.sim_output


class FakeTokenCounter:
    def __init__(self, response_content: str):
        self.response_content = response_content
        self.cur_tag = ""
        self.messages = []

    def set_cur_tag(self, tag: str):
        self.cur_tag = tag

    def count_chat(self, messages):
        self.messages = messages
        response = ChatResponse(
            message=ChatMessage(
                role=MessageRole.ASSISTANT,
                content=self.response_content,
            )
        )
        return response, object()


class RTLEditorRouteTests(unittest.TestCase):
    def test_normalize_repair_route_aliases(self):
        self.assertEqual(normalize_repair_route("syntax-repair"), "syntax")
        self.assertEqual(normalize_repair_route("interface/repair"), "interface")
        self.assertEqual(normalize_repair_route("logic_waveform"), "logic")
        self.assertEqual(normalize_repair_route("unknown"), "generic")

    def test_classify_failure_types(self):
        self.assertEqual(
            classify_debug_failure(
                is_syntax_pass=False,
                syntax_output=command_output(stderr="rtl.sv:3: syntax error"),
                is_sim_pass=False,
                sim_mismatch_cnt=0,
                sim_output="",
            ),
            "syntax",
        )
        self.assertEqual(
            classify_debug_failure(
                is_syntax_pass=True,
                syntax_output="Syntax check passed.",
                is_sim_pass=False,
                sim_mismatch_cnt=0,
                sim_output=command_output(
                    stderr="tb.sv:14: error: port `out` is not a port of dut."
                ),
            ),
            "interface",
        )
        self.assertEqual(
            classify_debug_failure(
                is_syntax_pass=True,
                syntax_output="Syntax check passed.",
                is_sim_pass=False,
                sim_mismatch_cnt=4,
                sim_output=command_output(
                    stdout="SIMULATION FAILED - 4 MISMATCHES DETECTED"
                ),
            ),
            "logic",
        )

    def test_mismatch_count_parses_generated_and_golden_logs(self):
        self.assertEqual(
            sim_review_mismatch_cnt(
                "SIMULATION FAILED - 4 MISMATCHES DETECTED, FIRST AT TIME 5"
            ),
            4,
        )
        self.assertEqual(
            sim_review_mismatch_cnt(
                "Hint: Output 'mux_in' has 38 mismatches. First mismatch occurred at time 5."
            ),
            38,
        )
        self.assertEqual(
            sim_review_mismatch_cnt("Mismatches: 12 in 60 samples"),
            12,
        )

    def test_interface_fix_can_advance_to_logic_route(self):
        sim_output = command_output(
            stdout="SIMULATION FAILED - 7 MISMATCHES DETECTED"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            rtl_path = Path(tmpdir) / "rtl.sv"
            old_rtl = "module top; assign out = a; endmodule\n"
            new_rtl = "module top; assign out = b; endmodule\n"
            rtl_path.write_text(new_rtl)
            editor = RTLEditor(
                token_counter=object(),
                sim_reviewer=FakeSimReviewer(False, 7, sim_output),
            )
            editor.output_dir_per_run = tmpdir
            editor.rtl_path = str(rtl_path)
            editor.repair_route = "interface"
            editor.last_mismatch_cnt = 0
            editor.last_failure_class = "interface"
            editor.last_error_signature = "previous interface error"

            with patch("mage.rtl_editor.check_syntax") as check_syntax:
                check_syntax.return_value = True, "Syntax check passed."
                ret = editor.judge_replace_action_execution(
                    "assign out = a;",
                    "assign out = b;",
                    "replace_content_by_matching",
                    old_rtl,
                )

            self.assertTrue(ret["is_action_executed"])
            self.assertEqual(editor.repair_route, "logic")
            self.assertEqual(rtl_path.read_text(), new_rtl)
            self.assertTrue((Path(tmpdir) / "debug_history.jsonl").exists())

    def test_logic_fix_rejects_interface_regression(self):
        sim_output = command_output(
            stderr="tb.sv:14: error: port `out` is not a port of dut."
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            rtl_path = Path(tmpdir) / "rtl.sv"
            old_rtl = "module top(output logic out); assign out = a; endmodule\n"
            new_rtl = "module wrong(output logic out); assign out = a; endmodule\n"
            rtl_path.write_text(new_rtl)
            editor = RTLEditor(
                token_counter=object(),
                sim_reviewer=FakeSimReviewer(False, 0, sim_output),
            )
            editor.output_dir_per_run = tmpdir
            editor.rtl_path = str(rtl_path)
            editor.repair_route = "logic"
            editor.last_mismatch_cnt = 3
            editor.last_failure_class = "logic"
            editor.last_error_signature = "previous mismatch"

            with patch("mage.rtl_editor.check_syntax") as check_syntax:
                check_syntax.return_value = True, "Syntax check passed."
                ret = editor.judge_replace_action_execution(
                    "module top",
                    "module wrong",
                    "replace_content_by_matching",
                    old_rtl,
                )

            self.assertFalse(ret["is_action_executed"])
            self.assertEqual(editor.repair_route, "logic")
            self.assertEqual(rtl_path.read_text(), old_rtl)

    def test_sim_judge_forces_rtl_route_in_golden_oracle_mode(self):
        token_counter = FakeTokenCounter(
            json.dumps(
                {
                    "reasoning": "The reference looks suspicious.",
                    "tb_needs_fix": True,
                    "error_route": "interface",
                }
            )
        )
        judge = SimJudge(token_counter)

        tb_needs_fix, error_route = judge.chat(
            input_spec="spec",
            failed_sim_log=command_output(stdout="SIMULATION FAILED"),
            failed_rtl="module TopModule; endmodule",
            failed_testbench="module tb; endmodule",
            allow_tb_fix=False,
        )

        self.assertFalse(tb_needs_fix)
        self.assertEqual(error_route, "interface")
        joined_prompt = "\n".join(str(message.content) for message in token_counter.messages)
        self.assertIn("golden benchmark oracle", joined_prompt)
        self.assertIn("MUST set tb_needs_fix to False", joined_prompt)


if __name__ == "__main__":
    unittest.main()
