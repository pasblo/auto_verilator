from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import sys

from filelist import generate_dynamic_file_list
from gtkwave_probe import update_gtkwave_view_from_sv
from project_context import resolve_runtime_config


def run_verilator_sim(
    top_module: str,
    testbench: str,
    conf_name: str | None = None,
    no_regenerate: bool = False,
    skip_verilate: bool = False,
    launch_gtkwave: bool = False,
    wave_file: str = "wave.fst",
    gtkwave_restore: bool = False,
    gtkwave_view: str | None = None,
    probe: bool = False,
    probe_view: str | None = None,
    probe_fresh: bool = False,
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

    tb_mod_name = tb_path.stem
    sim_label = top_module or tb_mod_name

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

    runtime.sim_dir.mkdir(parents=True, exist_ok=True)
    runtime.views_dir.mkdir(parents=True, exist_ok=True)

    cpp_path = runtime.sim_dir / "sim_main.cpp"
    _generate_main_cpp(tb_mod_name, cpp_path, wave_file, runtime.simulation_max_cycles)

    obj_dir = runtime.sim_dir / "obj_dir"
    if not skip_verilate:
        if obj_dir.exists():
            shutil.rmtree(obj_dir)
        obj_dir.mkdir(parents=True, exist_ok=True)

    verilated_dir = runtime.sim_dir / "verilated"
    verilated_dir.mkdir(parents=True, exist_ok=True)

    exe_name = f"sim_{sim_label}" + (".exe" if sys.platform.startswith("win") else "")
    exe_path = (verilated_dir / exe_name).resolve()

    if not skip_verilate:
        cmd = [
            runtime.verilator_bin,
            "-sv",
            "--cc",
            str(runtime.vlt_path),
            "-f",
            str(filelist_path),
            "--top-module",
            tb_mod_name,
            "--trace-fst",
            "--exe",
            cpp_path.name,
            "--build",
            "-j",
            "0",
            "-o",
            str(exe_path),
            str(tb_path),
        ]
        print("Running Verilator build...")
        build_result = subprocess.run(cmd, cwd=runtime.sim_dir)
        if build_result.returncode != 0:
            print(f"Verilator failed with exit code {build_result.returncode}", file=sys.stderr)
            return build_result.returncode
    else:
        if not exe_path.exists():
            print(f"Expected executable not found: {exe_path}", file=sys.stderr)
            return 1
        print(f"Skipping Verilator build. Reusing: {exe_path.name}")

    print("Running simulation...")
    run_result = subprocess.run([str(exe_path)], cwd=runtime.sim_dir)
    if run_result.returncode != 0:
        print(f"Simulation failed with exit code {run_result.returncode}", file=sys.stderr)
        return run_result.returncode

    wave_path = Path(wave_file)
    if not wave_path.is_absolute():
        wave_path = (runtime.sim_dir / wave_path).resolve()
    print(f"Simulation completed, waveform: {wave_path}")

    if probe:
        if probe_view is None:
            print("Probe requested but no GTKWave view resolved; skipping probe generation.")
        else:
            try:
                probe_info = update_gtkwave_view_from_sv(
                    sim_dir=str(runtime.sim_dir),
                    views_dir=str(runtime.views_dir),
                    wave_file=wave_file,
                    view_file=probe_view,
                    vlt_path=str(runtime.vlt_path),
                    tb_path=str(tb_path),
                    tb_mod_name=tb_mod_name,
                    filelist_path=str(filelist_path),
                    fresh=probe_fresh,
                )
                all_specs = probe_info.get("all", [])
                added_specs = probe_info.get("added", [])
                print(f"Probe summary: found {len(all_specs)} signals, added {len(added_specs)} signals.")
                print(f"Probe view updated: {probe_info.get('view_path', probe_view)}")
            except Exception as exc:
                print(f"Probe generation failed: {exc}", file=sys.stderr)

    if launch_gtkwave:
        _launch_gtkwave(
            runtime=runtime,
            wave_file=wave_file,
            gtkwave_restore=gtkwave_restore,
            gtkwave_view=gtkwave_view,
        )

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and run a SystemVerilog simulation with Verilator, optionally opening GTKWave."
    )
    parser.add_argument("top_module", help="Label for naming the generated executable.")
    parser.add_argument("testbench", help="Path to the SystemVerilog testbench file.")
    parser.add_argument(
        "gtkwave_view",
        nargs="?",
        default=None,
        help="Optional GTKWave .gtkw view file (relative to sim/gtk_views).",
    )
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
        "--skip-verilate",
        action="store_true",
        help="Skip Verilator build and run an existing executable.",
    )
    parser.add_argument(
        "--gtkwave-new",
        action="store_true",
        help="Launch GTKWave without restoring a .gtkw layout file.",
    )
    parser.add_argument(
        "--gtkwave-last",
        action="store_true",
        help="Launch GTKWave restoring the last view used by this script.",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Generate/update a GTKWave view using GTK probe comments in SystemVerilog.",
    )
    parser.add_argument(
        "--probe-add",
        action="store_true",
        help="Append probe signals in-place to the selected .gtkw view file.",
    )
    parser.add_argument(
        "--probe-out",
        type=str,
        default=None,
        help="Write probe output to this .gtkw file name (relative to sim/gtk_views).",
    )
    parser.add_argument(
        "--wavefile",
        type=str,
        default="wave.fst",
        help="Waveform file path (absolute or relative to sim/verilator).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        runtime = resolve_runtime_config(Path(__file__).resolve().parent, args.conf)
    except (FileNotFoundError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    launch_gtkwave = False
    gtkwave_restore = False
    gtkwave_view = None
    last_view = None

    if args.gtkwave_new:
        launch_gtkwave = True
    elif args.gtkwave_view:
        launch_gtkwave = True
        gtkwave_restore = True
        gtkwave_view = args.gtkwave_view
        _remember_last_view(runtime, gtkwave_view)
    elif args.gtkwave_last:
        launch_gtkwave = True
        last_view = _resolve_last_view(runtime)
        if last_view:
            gtkwave_restore = True
            gtkwave_view = last_view
            _remember_last_view(runtime, gtkwave_view)
        else:
            print("No previous GTKWave view found; opening without restore.")

    probe_enabled = args.probe or args.probe_add
    probe_view, probe_fresh = _resolve_probe_target(
        runtime=runtime,
        probe_enabled=probe_enabled,
        probe_out=args.probe_out,
        probe_add=args.probe_add,
        selected_view=args.gtkwave_view,
        use_last_view=args.gtkwave_last,
        last_view=last_view,
        wavefile=args.wavefile,
    )

    if launch_gtkwave and probe_enabled and probe_view:
        gtkwave_restore = True
        gtkwave_view = probe_view

    return run_verilator_sim(
        top_module=args.top_module,
        testbench=args.testbench,
        conf_name=args.conf,
        no_regenerate=args.no_regenerate,
        skip_verilate=args.skip_verilate,
        launch_gtkwave=launch_gtkwave,
        wave_file=args.wavefile,
        gtkwave_restore=gtkwave_restore,
        gtkwave_view=gtkwave_view,
        probe=probe_enabled,
        probe_view=probe_view,
        probe_fresh=probe_fresh,
    )


def _generate_main_cpp(tb_mod_name: str, output_path: Path, wave_file: str, max_cycles: int) -> None:
    tb_class = "V" + tb_mod_name
    code = f"""// Verilator simulation harness (auto-generated)
#include "verilated.h"
#include "{tb_class}.h"
#include "verilated_fst_c.h"

vluint64_t main_time = 0;
double sc_time_stamp() {{
    return main_time;
}}

int main(int argc, char** argv) {{
    Verilated::commandArgs(argc, argv);
    {tb_class}* top = new {tb_class};

    Verilated::traceEverOn(true);
    VerilatedFstC* tfp = new VerilatedFstC;
    top->trace(tfp, 99);
    tfp->open("{wave_file}");

    const vluint64_t max_time = {max_cycles};
    while (!Verilated::gotFinish() && main_time < max_time) {{
        top->eval();
        tfp->dump(main_time);
        main_time++;
    }}

    top->final();
    tfp->close();
    delete tfp;
    delete top;
    return 0;
}}
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(code, encoding="utf-8")


def _resolve_probe_target(
    runtime,
    probe_enabled: bool,
    probe_out: str | None,
    probe_add: bool,
    selected_view: str | None,
    use_last_view: bool,
    last_view: str | None,
    wavefile: str,
) -> tuple[str | None, bool]:
    if not probe_enabled:
        return None, False

    base_view = selected_view
    if use_last_view and not base_view:
        base_view = last_view or _resolve_last_view(runtime)
    if not base_view:
        base_view = Path(wavefile).stem + ".gtkw"

    if probe_out:
        target_view = probe_out
    elif probe_add:
        target_view = base_view
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = Path(base_view)
        target_view = f"{base.stem}_{stamp}{base.suffix or '.gtkw'}"

    base_abs = _resolve_view_path(runtime, base_view)
    target_abs = _resolve_view_path(runtime, target_view)

    probe_fresh = False
    if base_abs != target_abs:
        if base_abs.exists():
            target_abs.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(base_abs, target_abs)
        else:
            probe_fresh = True
    elif not target_abs.exists():
        probe_fresh = True

    _remember_last_view(runtime, target_view)
    return target_view, probe_fresh


def _remember_last_view(runtime, view_name: str) -> None:
    runtime.views_dir.mkdir(parents=True, exist_ok=True)
    runtime.last_gtkwave_view_path.write_text(view_name, encoding="utf-8")


def _resolve_last_view(runtime) -> str | None:
    if runtime.last_gtkwave_view_path.exists():
        saved = runtime.last_gtkwave_view_path.read_text(encoding="utf-8").strip()
        if saved:
            return saved

    candidates = sorted(runtime.views_dir.glob("*.gtkw"), key=lambda path: path.stat().st_mtime)
    if candidates:
        latest = candidates[-1].name
        print(f"No recorded last view; using latest in folder: {latest}")
        return latest
    return None


def _resolve_view_path(runtime, view: str) -> Path:
    path = Path(view)
    if path.is_absolute():
        return path.resolve()
    return (runtime.views_dir / path).resolve()


def _launch_gtkwave(runtime, wave_file: str, gtkwave_restore: bool, gtkwave_view: str | None) -> None:
    cmd = [runtime.gtkwave_bin]
    if gtkwave_restore and gtkwave_view:
        view_path = _resolve_view_path(runtime, gtkwave_view)
        if view_path.exists():
            cmd.extend(["-a", str(view_path)])
            print(f"Restoring GTKWave view: {view_path}")
        else:
            print(f"GTKWave view file not found: {view_path}. Opening without restore.")

    wave_path = Path(wave_file)
    if not wave_path.is_absolute():
        wave_path = runtime.sim_dir / wave_path
    cmd.append(str(wave_path))

    try:
        subprocess.Popen(cmd, cwd=runtime.sim_dir)
        print("Opening GTKWave...")
    except FileNotFoundError:
        print("GTKWave not found in PATH. Open the waveform file manually.", file=sys.stderr)


def _resolve_user_path(path_value: str) -> Path:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


if __name__ == "__main__":
    sys.exit(main())
