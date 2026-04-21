# auto_verilator

Project-agnostic Verilator + GTKWave automation for SystemVerilog projects.

This repository is designed to be used as a git submodule under `scripts/auto_verilator` and provides two main CLI flows:

1. `lint` for lint-only checks
2. `sim` for build + run simulation

## Host Project Layout

Expected structure in the host project:

```text
<project-root>/
|-- rtl/
|   `-- ... SystemVerilog sources ...
|-- sim/
|   |-- verilator/   # generated file list, obj_dir, binaries, waveforms
|   `-- gtk_views/   # .gtkw files and last-view state
`-- scripts/
    |-- av.conf
    |-- verilator_conf.vlt
    `-- auto_verilator/   # this submodule
```

## Install As Submodule

```bash
git submodule add https://github.com/pasblo/auto_verilator scripts/auto_verilator
git submodule update --init --recursive
```

## Required Config Files

Create these files in the host project `scripts/` folder:

1. `av.conf`
2. `verilator_conf.vlt`

Templates provided in this repo:

- `av.conf.example`
- `verilator_conf.vlt.example`

## `av.conf` Details

`av.conf` controls project paths and default tool behavior. It uses an INI-like format:

- Sections: `[paths]`, `[verilator]`, `[tools]`
- Keys: `KEY = VALUE` or `KEY: VALUE`
- Comments: lines starting with `#`, `;`, or `//`
- Relative paths are resolved from the host `scripts/` directory

Example:

```ini
[paths]
RTL_DIR = ../rtl
SIM_ROOT = ../sim
VERILATOR_CONF_VLT = ./verilator_conf.vlt
# SIM_DIR = ../sim/verilator
# GTKWAVE_VIEWS_DIR = ../sim/gtk_views

[verilator]
HDL_EXTENSIONS = sv
EXCLUDE_FOLDERS = tests
EXCLUDE_TESTBENCHES = true
FOLDER_ORDER = constants, interfaces, interstage, components
SIMULATION_MAX_CYCLES = 9999999
FILELIST_FLAGS = -Wall; -Wno-fatal; -j 0; --assert; --no-trace-top; --trace-structs; --timing; --x-initial unique

[tools]
VERILATOR_BIN = verilator
GTKWAVE_BIN = gtkwave
```

Key reference:

| Section | Key | Meaning |
|---|---|---|
| `[paths]` | `RTL_DIR` | Folder scanned recursively for HDL files. |
| `[paths]` | `SIM_ROOT` | Base simulation folder. Default subfolders are derived from it. |
| `[paths]` | `SIM_DIR` | Optional explicit override for Verilator working/output folder. |
| `[paths]` | `GTKWAVE_VIEWS_DIR` | Optional explicit override for `.gtkw` views folder. |
| `[paths]` | `VERILATOR_CONF_VLT` | Path to the Verilator `.vlt` config/waiver file. |
| `[verilator]` | `HDL_EXTENSIONS` | Comma-separated HDL extensions to include (example: `sv,v`). |
| `[verilator]` | `EXCLUDE_FOLDERS` | Comma-separated folder names to skip while scanning `RTL_DIR`. |
| `[verilator]` | `EXCLUDE_TESTBENCHES` | Boolean true or false indicating if testbench files "_tb" are expluded in `verilator.f`. |
| `[verilator]` | `FOLDER_ORDER` | Source ordering priority by folder name for `verilator.f`. |
| `[verilator]` | `SIMULATION_MAX_CYCLES` | Max simulation loop cycles in generated C++ harness. |
| `[verilator]` | `FILELIST_FLAGS` | Extra flags written to `verilator.f`. Use `;` separator for flags containing spaces. |
| `[tools]` | `VERILATOR_BIN` | Verilator executable name/path. |
| `[tools]` | `GTKWAVE_BIN` | GTKWave executable name/path. |

Config lookup behavior:

1. If `--conf` is passed, that file is used.
2. Else `scripts/av.conf` is used when present.
3. Else if exactly one `*.conf` exists in `scripts/`, that file is used.
4. Else execution fails and asks for explicit `--conf`.

## `verilator_conf.vlt` Explained

This file is passed directly to Verilator in both `lint` and `sim` flows. Use it for lint control, waivers, and Verilator configuration directives.

Minimal file:

```text
`verilator_config
```

Example with waivers:

```text
`verilator_config
// Ignore UNUSED warnings in testbench files
lint_off -rule UNUSED -file "*_tb.sv"
// Ignore module/file naming mismatch globally
lint_off -rule DECLFILENAME -file "*"
```

Guidelines:

1. Keep waivers targeted by `-file` patterns.
2. Prefer waiving testbench-only noise first.
3. Do not over-waive design warnings you still want to catch.

## CLI Entry Points

You can run through the dispatcher:

```bash
python scripts/auto_verilator/av.py <command> ...
```

Or call scripts directly:

```bash
python scripts/auto_verilator/lint.py ...
python scripts/auto_verilator/simulate.py ...
```

## Command: `lint`

Syntax:

```bash
python scripts/auto_verilator/av.py lint <testbench> [--conf <conf>] [--no-regenerate] [--latex [<tex_path>]]
```

Arguments:

| Argument | Required | Meaning |
|---|---|---|
| `testbench` | Yes | Path to the testbench file to lint. |
| `--conf` | No | Config file path/name. If omitted, lookup rules above apply. |
| `--no-regenerate` | No | Reuse existing `sim/verilator/verilator.f` without rescanning `rtl/`. |
| `--latex [path]` | No | Save lint stdout/stderr as a minimal LaTeX verbatim file. If no path is given, uses `lint_output.tex` in current directory. |

Examples:

```bash
# Basic lint run
python scripts/auto_verilator/av.py lint rtl/tests/alu/alu_tb.sv

# Use explicit config file
python scripts/auto_verilator/av.py lint rtl/tests/alu/alu_tb.sv --conf av_fast.conf

# Reuse existing verilator.f
python scripts/auto_verilator/av.py lint rtl/tests/alu/alu_tb.sv --no-regenerate

# Write LaTeX report with default filename
python scripts/auto_verilator/av.py lint rtl/tests/alu/alu_tb.sv --latex

# Write LaTeX report to explicit path
python scripts/auto_verilator/av.py lint rtl/tests/alu/alu_tb.sv --latex docs/lint/alu.tex
```

## Command: `sim`

Syntax:

```bash
python scripts/auto_verilator/av.py sim <top_module_label> <testbench> [gtkwave_view] [options]
```

Arguments:

| Argument | Required | Meaning |
|---|---|---|
| `top_module_label` | Yes | Label used to name executable (`sim_<label>`). |
| `testbench` | Yes | Path to testbench file. The testbench filename stem is used as Verilator `--top-module`. |
| `gtkwave_view` | No | `.gtkw` view name/path to restore when GTKWave restore mode is active. |
| `--conf` | No | Config file path/name. |
| `--no-regenerate` | No | Reuse existing `verilator.f`. |
| `--skip-verilate` | No | Skip build; run existing executable from `sim/verilator/verilated/`. |
| `--wavefile` | No | Waveform output name/path. Relative paths are resolved under `sim/verilator`. |
| `--gtkwave-new` | No | Launch GTKWave without restoring a `.gtkw` file. |
| `--gtkwave-last` | No | Launch GTKWave restoring last used view from `sim/gtk_views/.last_gtkwave_view`. |
| `--probe` | No | Generate/update a GTKWave view from `// GTK - ...` comments. |
| `--probe-add` | No | Append probes in-place to selected/base `.gtkw` view. |
| `--probe-out` | No | Output `.gtkw` name/path for probe-generated view. |

Examples:

```bash
# Build and run simulation
python scripts/auto_verilator/av.py sim alu rtl/tests/alu/alu_tb.sv

# Reuse existing filelist and executable
python scripts/auto_verilator/av.py sim alu rtl/tests/alu/alu_tb.sv --no-regenerate --skip-verilate

# Save waveform with custom name
python scripts/auto_verilator/av.py sim alu rtl/tests/alu/alu_tb.sv --wavefile alu_wave.fst

# Open GTKWave fresh
python scripts/auto_verilator/av.py sim alu rtl/tests/alu/alu_tb.sv --gtkwave-new

# Restore a specific view
python scripts/auto_verilator/av.py sim alu rtl/tests/alu/alu_tb.sv alu_debug.gtkw

# Restore the last view used
python scripts/auto_verilator/av.py sim alu rtl/tests/alu/alu_tb.sv --gtkwave-last

# Generate probe-based view (new timestamped file)
python scripts/auto_verilator/av.py sim alu rtl/tests/alu/alu_tb.sv --probe

# Append probes into an existing view
python scripts/auto_verilator/av.py sim alu rtl/tests/alu/alu_tb.sv alu_debug.gtkw --probe-add

# Write probes to a specific output view
python scripts/auto_verilator/av.py sim alu rtl/tests/alu/alu_tb.sv --probe --probe-out alu_probe.gtkw
```

## SystemVerilog Comment Conventions

`simulate.py --probe` reads GTK annotations from SV comments.

Module color:

```systemverilog
module my_mod; // GTK - Blue
```

Signal format:

```systemverilog
logic [31:0] addr;  // GTK - Hex
logic [15:0] cnt;   // GTK - Probe, Dec
logic signed [7:0] temp; // GTK - SDec
```

Supported colors:

- `Green`
- `Red`
- `Orange`
- `Yellow`
- `Blue`
- `Indigo`
- `Violet`

Supported formats:

- `Hex`
- `Dec`
- `SDec`
- `Bin`
- `Oct`

SV file exclusion:

- Any file containing `VERILATOR_SKIP` in its first ~400 characters is skipped by file discovery.

## Installing Verilator and GTKWave (Windows)

In WSL: `wsl.exe -d Ubuntu`

```bash
sudo apt-get update
sudo apt-get install -y verilator gtkwave
verilator --version
```

MSYS2 MinGW64:

```bash
pacman -Syuu
pacman -S --needed mingw-w64-x86_64-verilator mingw-w64-x86_64-gtkwave
verilator --version
```

## Suggested Host `.gitignore`

```gitignore
sim/
```
