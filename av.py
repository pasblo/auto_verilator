from __future__ import annotations

import sys

import lint
import simulate


USAGE = """Usage:
  python scripts/auto_verilator/av.py lint  <lint args...>
  python scripts/auto_verilator/av.py sim   <sim args...>

Run with -h after any subcommand for full options.
"""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        print(USAGE)
        return 0

    command, rest = args[0], args[1:]
    if command == "lint":
        return lint.main(rest)
    if command == "sim":
        return simulate.main(rest)

    print(f"Unknown command: {command}", file=sys.stderr)
    print(USAGE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
