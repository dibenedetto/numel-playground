import json
import sys
import unittest

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from prompt_stack import PLANNER_MODE_DIRECTIVE


class PromptStackTests(unittest.TestCase):
    def test_console_base_instructions_reference_operating_contracts(self):
        data = json.loads((ROOT / "app" / "console_agent.json").read_text(encoding="utf-8"))
        instructions = "\n".join(data["options"]["instructions"])
        self.assertIn("[Workflow Generation Contract]", instructions)
        self.assertIn("[Planner Instructions]", instructions)

    def test_planner_instructions_use_full_workflow_replacement_contract(self):
        text = (ROOT / "app" / "planner_instructions.txt").read_text(encoding="utf-8")
        self.assertIn("Numel will apply it automatically", text)
        self.assertNotIn("Call add_node() for each node, then connect() for each edge.", text)
        self.assertIn("Do not narrate incremental `add_node()` / `connect()` steps", text)

    def test_planner_context_orders_contract_before_behavior(self):
        text = (ROOT / "app" / "console.py").read_text(encoding="utf-8")
        start = text.index('planner_ctx = ""')
        end = text.index('\n\t\treturn {', start)
        block = text[start:end]
        self.assertLess(block.index("[Workflow Generation Contract]"), block.index("[Planner Instructions]"))
        self.assertNotIn("[Available Resources]", block)

    def test_generation_prompt_has_compiler_role(self):
        text = (ROOT / "app" / "api.py").read_text(encoding="utf-8")
        self.assertIn("You are Numel Workflow Generator", text)
        self.assertIn("## Response Contract", text)

    def test_shared_planner_mode_directive_mentions_json_application(self):
        self.assertIn("```json code block", PLANNER_MODE_DIRECTIVE)
        self.assertIn("Numel can apply it automatically", PLANNER_MODE_DIRECTIVE)


if __name__ == "__main__":
    unittest.main()
