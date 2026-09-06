"""Load fixture payer policies from markdown and pick the best match for intake."""

from __future__ import annotations

import json
from pathlib import Path

from pauth.schemas import PolicyChecklist, PolicyItem

POLICIES_DIR = Path(__file__).resolve().parent.parent / "policies"


def _parse_markdown(path: Path) -> PolicyChecklist:
    """Parse heading, metadata lines, and numbered criteria from a fixture file."""
    lines = path.read_text(encoding="utf-8").splitlines()
    payer = ""
    policy_id = path.stem
    title = path.stem
    procedure = ""
    items: list[PolicyItem] = []
    for raw in lines:
        line = raw.strip()
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.lower().startswith("payer:"):
            payer = line.split(":", 1)[1].strip()
        elif line.lower().startswith("policy id:"):
            policy_id = line.split(":", 1)[1].strip()
        elif line.lower().startswith("procedure:"):
            procedure = line.split(":", 1)[1].strip()
        elif line[:1].isdigit() and ". " in line[:5]:
            text = line.split(". ", 1)[1].strip()
            items.append(PolicyItem(id=f"{policy_id}-{len(items) + 1}", text=text))
    if not items:
        items.append(
            PolicyItem(
                id=f"{policy_id}-1",
                text=f"Medical necessity documented for {procedure or title}.",
            )
        )
    return PolicyChecklist(
        payer=payer,
        policy_id=policy_id,
        title=title,
        items=items,
        source=str(path.name),
    )


def load_policies() -> list[PolicyChecklist]:
    """Read every `*.md` fixture under `pauth/policies/`."""
    return [_parse_markdown(path) for path in sorted(POLICIES_DIR.glob("*.md"))]


def retrieve_policy(payer: str, procedure: str, cpt: str) -> PolicyChecklist:
    """Score fixtures by CPT, then payer name, then procedure tokens; always return one."""
    policies = load_policies()
    needle_payer = payer.lower()
    needle_cpt = cpt.lower().strip()
    needle_proc = procedure.lower()

    scored: list[tuple[int, PolicyChecklist]] = []
    for policy in policies:
        score = 0
        blob = json.dumps(policy.model_dump()).lower()
        if needle_payer and needle_payer.split()[0] in policy.payer.lower():
            score += 5
        if needle_cpt and needle_cpt in blob:
            score += 8
        if needle_proc:
            for token in needle_proc.replace(",", " ").split():
                if len(token) > 3 and token in blob:
                    score += 1
        scored.append((score, policy))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    if scored and scored[0][0] > 0:
        return scored[0][1]
    return policies[0]
