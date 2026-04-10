from typing import Iterable, List, Optional

CONNECTED_TOOLKITS_SECTION_TITLE = "Connected Toolkits"
CONNECTED_TOOLKITS_SECTION_INTRO = (
    "These toolkit descriptions explain external capabilities available to the current agent."
)

PLANNER_MODE_DIRECTIVE = (
    "You are in PLANNER MODE for Numel.\n"
    "Your job is to inspect the current space, decide the next best workflow state, "
    "and guide or apply that state.\n"
    "Use tools to inspect context, run workflows, and evaluate results.\n"
    "When the workflow should change, return exactly one complete workflow inside a "
    "```json code block so Numel can apply it automatically.\n"
    "If no workflow change is needed, respond briefly in normal prose.\n"
    "When autonomous refinement is in scope, preserve or add eval_flow nodes so quality can be measured."
)


def extend_instruction_block(
    instructions: Optional[List[str]],
    title: str,
    entries: Optional[Iterable[str]],
    intro: Optional[str] = None,
) -> List[str]:
    merged = list(instructions or [])
    clean = [str(entry).strip() for entry in (entries or []) if str(entry).strip()]
    if not clean:
        return merged
    merged.append(f"\n## {title}")
    if intro:
        merged.append(intro)
    merged.extend(clean)
    return merged
