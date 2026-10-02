"""Runs the numbered SQL steps in `orders_pipeline/sql/` in file-name order."""

from importlib import resources


def _prefix(name):
    return name.split("_", 1)[0]


def sql_steps():
    folder = resources.files("orders_pipeline").joinpath("sql")
    return sorted(
        (p for p in folder.iterdir() if p.name.endswith(".sql")), key=lambda p: p.name
    )


def run_steps(con, upto=None, start=None, log=None):
    """Execute the SQL steps.

    `start` skips steps whose prefix sorts before it; `upto` stops after the step
    whose prefix equals it. Both are prefixes such as "10" or "62".
    """
    for step in sql_steps():
        prefix = _prefix(step.name)
        if start is not None and prefix < start:
            continue
        con.execute(step.read_text(encoding="utf-8"))
        if log:
            log("step_done", step=step.name)
        if upto is not None and prefix == upto:
            break
