from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

from filelist import generate_dynamic_file_list
from project_context import resolve_runtime_config


def run_verilator_lint(
    testbench: str,
    conf_name: str | None = None,
    no_regenerate: bool = False,
    latex_output: str | None = None,
) -> int:
    try:
        runtime = resolve_runtime_config(Path(__file__).resolve().parent, conf_name)
    except (FileNotFoundError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    tb_path = _resolve_user_path(testbench)
    if not tb_path.exists():
        print(f"Testbench file not found: {tb_path}", file=sys.stderr)
        return 1

    if not runtime.vlt_path.exists():
        print(
            f"Verilator config file not found: {runtime.vlt_path}\n"
            "Create it in your scripts folder or set VERILATOR_CONF_VLT in the .conf file.",
            file=sys.stderr,
        )
        return 1

    if no_regenerate:
        if not runtime.filelist_path.exists():
            print(
                f"Missing file list: {runtime.filelist_path}\n"
                "Run without --no-regenerate once to generate it.",
                file=sys.stderr,
            )
            return 1
        filelist_path = runtime.filelist_path
    else:
        try:
            filelist_path = generate_dynamic_file_list(runtime, tb_path=tb_path)
        except (FileNotFoundError, ValueError) as exc:
            print(exc, file=sys.stderr)
            return 1

    cmd = [
        runtime.verilator_bin,
        "-sv",
        "--lint-only",
        str(runtime.vlt_path),
        "-f",
        str(filelist_path),
        str(tb_path),
    ]

    result = subprocess.run(cmd, cwd=runtime.sim_dir, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    if latex_output is not None:
        latex_path = _resolve_user_path(latex_output)
        _write_latex_output(latex_path, result.stdout, result.stderr)
        print(f"LaTeX output saved to {latex_path}")

    if result.returncode != 0:
        print(f"Verilator linting failed with exit code {result.returncode}", file=sys.stderr)
    else:
        print("Linting completed.")

    return result.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lint a SystemVerilog testbench and RTL sources using Verilator."
    )
    parser.add_argument("testbench", help="Path to the SystemVerilog testbench file.")
    parser.add_argument(
        "--conf",
        default=None,
        help="Configuration file name/path. If omitted, scripts/av.conf is used by default.",
    )
    parser.add_argument(
        "--no-regenerate",
        action="store_true",
        help="Reuse existing verilator.f instead of rescanning rtl/.",
    )
    parser.add_argument(
        "--latex",
        nargs="?",
        const="lint_output.tex",
        default=None,
        help="Optionally save output as a minimal LaTeX file. "
        "If no path is provided, writes lint_output.tex in the current directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_verilator_lint(
        testbench=args.testbench,
        conf_name=args.conf,
        no_regenerate=args.no_regenerate,
        latex_output=args.latex,
    )


def _resolve_user_path(path_value: str) -> Path:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def _write_latex_output(latex_path: Path, stdout_text: str, stderr_text: str) -> None:
    latex_path.parent.mkdir(parents=True, exist_ok=True)
    with latex_path.open("w", encoding="utf-8") as out_file:
        out_file.write("% Auto-generated from Verilator lint output\n")
        out_file.write("\\begin{verbatim}\n")
        out_file.write(stdout_text)
        out_file.write(stderr_text)
        out_file.write("\\end{verbatim}\n")


if __name__ == "__main__":
    sys.exit(main())
