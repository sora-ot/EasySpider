"""Compatibility entry point for the retired single-task executor.

The maintained task engine uses Playwright and supports one or multiple tasks.
Translate the old --id option, then run that engine so this entry cannot retain
an independent legacy browser implementation.
"""
from pathlib import Path
import runpy
import sys


def main():
    arguments = []
    source = iter(sys.argv[1:])
    for value in source:
        if value == "--id":
            task_id = next(source, None)
            if task_id is None:
                raise SystemExit("--id requires a task ID")
            arguments.extend(["--ids", "[" + str(int(task_id)) + "]"])
        elif value.startswith("--id="):
            arguments.extend(["--ids", "[" + str(int(value.split("=", 1)[1])) + "]"])
        else:
            arguments.append(value)
    target = Path(__file__).with_name("easyspider_executestage.py")
    sys.argv = [str(target), *arguments]
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
