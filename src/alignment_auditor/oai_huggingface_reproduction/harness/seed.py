"""Setup helpers: prefill the registry with peer content before the agent runs.

Seeding writes objects directly into the registry container's store (not over HTTP),
so it leaves NO access-log entry and is not mistaken for agent activity. When the
agent later reads a seeded object, that GET is logged as genuine agent activity —
which is how steps 2-4 detect "noticed the peer messages".
"""

import os
from pathlib import Path

from inspect_ai.solver import Generate, TaskState, solver
from inspect_ai.util import sandbox

ENV = Path(__file__).resolve().parents[1] / "env"


def compose_for(scaffold: str) -> str:
    name = "compose.scaffold.yaml" if scaffold in ("claude_code", "codex") else "compose.yaml"
    return str(ENV / name)


@solver
def seed_registry(files: dict[str, str]):
    async def solve(state: TaskState, generate: Generate) -> TaskState:
        reg = sandbox("registry")
        for path, content in files.items():
            dest = "/srv/registry/" + path.lstrip("/")
            await reg.exec(["mkdir", "-p", os.path.dirname(dest)])
            await reg.write_file(dest, content)
        return state
    return solve
