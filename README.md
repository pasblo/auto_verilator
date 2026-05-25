# auto_verilator

Project-agnostic Verilator + GTKWave automation for SystemVerilog projects.

Designed to be vendored as a git submodule under `scripts/auto_verilator`. It
discovers RTL sources, generates a Verilator filelist, builds a C++ harness
around your testbench, runs the simulation, and optionally opens GTKWave
with a saved view.

Two CLI flows:

- `lint` — lint-only check of the RTL and a testbench
- `sim`  — build + run, with optional waveform and GTKWave launch

---

## Host Project Layout

```text
<project-root>/
|-- rtl/                            # SystemVerilog sources
|-- sim/
|   |-- verilator/                  # generated filelist, obj_dir, binaries, waveforms
|   `-- gtk_views/                  # .gtkw view files and last-view state
`-- scripts/
    |-- av.conf                     # auto_verilator config (see below)
    |-- verilator_conf.vlt          # Verilator lint waivers / directives
    `-- auto_verilator/             # this submodule
```

## Install As Submodule

```bash
git submodule add https://github.com/pasblo/auto_verilator scripts/auto_verilator
git submodule update --init --recursive
```

Then copy the two example config files into the host `scripts/` directory:

```bash
cp scripts/auto_verilator/av.conf.example          scripts/av.conf
cp scripts/auto_verilator/verilator_conf.vlt.example scripts/verilator_conf.vlt
```

## Suggested Host `.gitignore`

```gitignore
sim/
```

---

## Configuration: `av.conf`

INI-style file controlling paths and tool defaults.

- Sections: `[paths]`, `[verilator]`, `[tools]`
- `KEY = VALUE` or `KEY: VALUE`
- Comments: lines starting with `#`, `;`, or `//`
- Relative paths are resolved from the host `scripts/` directory

Example (`av.conf.example`):

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
| `[paths]` | `SIM_ROOT` | Base simulation folder. Subfolders are derived from it unless overridden. |
| `[paths]` | `SIM_DIR` | Optional explicit override for the Verilator working/output folder. |
| `[paths]` | `GTKWAVE_VIEWS_DIR` | Optional explicit override for the `.gtkw` views folder. |
| `[paths]` | `VERILATOR_CONF_VLT` | Path to the Verilator `.vlt` config/waiver file. |
| `[verilator]` | `HDL_EXTENSIONS` | Comma-separated HDL extensions to include (e.g. `sv,v`). |
| `[verilator]` | `EXCLUDE_FOLDERS` | Comma-separated folder names skipped during the `RTL_DIR` scan. |
| `[verilator]` | `EXCLUDE_TESTBENCHES` | If `true`, files ending in `_tb.sv` are excluded from `verilator.f`. |
| `[verilator]` | `FOLDER_ORDER` | Source ordering priority by folder name for `verilator.f`. |
| `[verilator]` | `SIMULATION_MAX_CYCLES` | Max simulation loop cycles in the generated C++ harness. |
| `[verilator]` | `FILELIST_FLAGS` | Flags appended to `verilator.f`. Use `;` separator for flags containing spaces. |
| `[tools]` | `VERILATOR_BIN` | Verilator executable name/path. |
| `[tools]` | `GTKWAVE_BIN` | GTKWave executable name/path. |

### Config lookup order

1. If `--conf <path>` is passed, that file is used.
2. Else `scripts/av.conf` is used when present.
3. Else if exactly one `*.conf` exists in `scripts/`, that file is used.
4. Otherwise execution fails and asks for an explicit `--conf`.

`--conf` accepts either a file name relative to `scripts/` (e.g. `av_fast.conf`)
or an absolute path.

## Configuration: `verilator_conf.vlt`

Passed directly to Verilator in both `lint` and `sim` flows. Use it for lint
waivers and other Verilator configuration directives.

Minimal file:

```text
`verilator_config
```

With waivers:

```text
`verilator_config
// Ignore UNUSED warnings in testbench files
lint_off -rule UNUSED -file "*_tb.sv"
// Ignore module/file naming mismatch globally
lint_off -rule DECLFILENAME -file "*"
```

Keep waivers targeted by `-file` patterns — don't over-waive design warnings
you still want to catch.

---

## CLI Entry Points

Use the dispatcher:

```bash
python scripts/auto_verilator/av.py <command> ...
```

Or call the subcommand scripts directly:

```bash
python scripts/auto_verilator/lint.py     ...
python scripts/auto_verilator/simulate.py ...
```

## Command: `lint`

```bash
python scripts/auto_verilator/av.py lint <testbench> [--conf <conf>] [--no-regenerate] [--latex [<tex_path>]]
```

| Argument | Required | Meaning |
|---|---|---|
| `testbench` | Yes | Path to the testbench file to lint. |
| `--conf` | No | Config file path/name. If omitted, the lookup order above is used. |
| `--no-regenerate` | No | Reuse the existing `sim/verilator/verilator.f` without rescanning `rtl/`. |
| `--latex [path]` | No | Save lint stdout/stderr as a minimal LaTeX verbatim file. If no path is given, writes `lint_output.tex` in the current directory. |

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

```bash
python scripts/auto_verilator/av.py sim <top_module_label> <testbench> [gtkwave_view] [options]
```

| Argument | Required | Meaning |
|---|---|---|
| `top_module_label` | Yes | Label used to name the executable (`sim_<label>`). |
| `testbench` | Yes | Path to the testbench file. Its filename stem is used as Verilator `--top-module`. |
| `gtkwave_view` | No | `.gtkw` view name/path to restore when GTKWave launches. |
| `--conf` | No | Config file path/name. |
| `--no-regenerate` | No | Reuse the existing `verilator.f`. |
| `--skip-verilate` | No | Skip the build and run the existing executable from `sim/verilator/verilated/`. |
| `--trace-format {fst,vcd,none}` | No | Waveform format (default `fst`). See below. |
| `--fast` | No | Shortcut for `--trace-format none`. |
| `--vcd` | No | Shortcut for `--trace-format vcd`. |
| `--wavefile` | No | Waveform output name/path. Relative paths are resolved under `sim/verilator`. |
| `--gtkwave-new` | No | Launch GTKWave without restoring a `.gtkw` file. |
| `--gtkwave-last` | No | Launch GTKWave restoring the last view used. |
| `--probe` | No | Generate a fresh GTKWave view from `// GTK - ...` comments in the SV sources. |
| `--probe-add` | No | Append probes in-place to the selected/base `.gtkw` view. |
| `--probe-out` | No | Output `.gtkw` name/path for the probe-generated view. |

### Trace format choices

| Value | Effect |
|---|---|
| `fst` (default) | GTKWave-friendly; compact. Compatible with `--probe`, `--gtkwave-*`. |
| `vcd` | 4-state VCD. Larger on disk but consumable by tools like OpenSTA's `read_vcd`. |
| `none` | No waveform; trace instrumentation is dropped entirely for the fastest build. Self-checking testbenches still report PASS/FAIL. GTKWave/probe options are ignored in this mode. |

Examples:

```bash
# Build and run with the default FST waveform
python scripts/auto_verilator/av.py sim alu rtl/tests/alu/alu_tb.sv

# Reuse filelist and executable
python scripts/auto_verilator/av.py sim alu rtl/tests/alu/alu_tb.sv --no-regenerate --skip-verilate

# Custom waveform name
python scripts/auto_verilator/av.py sim alu rtl/tests/alu/alu_tb.sv --wavefile alu_wave.fst

# VCD output (e.g. for OpenSTA)
python scripts/auto_verilator/av.py sim alu rtl/tests/alu/alu_tb.sv --vcd

# Fast self-check, no waveform
python scripts/auto_verilator/av.py sim alu rtl/tests/alu/alu_tb.sv --fast

# Open GTKWave fresh
python scripts/auto_verilator/av.py sim alu rtl/tests/alu/alu_tb.sv --gtkwave-new

# Restore a specific view
python scripts/auto_verilator/av.py sim alu rtl/tests/alu/alu_tb.sv alu_debug.gtkw

# Restore the last view used
python scripts/auto_verilator/av.py sim alu rtl/tests/alu/alu_tb.sv --gtkwave-last

# Generate a probe-based view (new timestamped file)
python scripts/auto_verilator/av.py sim alu rtl/tests/alu/alu_tb.sv --probe

# Append probes to an existing view
python scripts/auto_verilator/av.py sim alu rtl/tests/alu/alu_tb.sv alu_debug.gtkw --probe-add

# Write probes to a specific output view
python scripts/auto_verilator/av.py sim alu rtl/tests/alu/alu_tb.sv --probe --probe-out alu_probe.gtkw
```

---

## SystemVerilog Comment Conventions

The `--probe` flow reads `// GTK - ...` annotations from SystemVerilog files.

Module color (applied to all probes inside the module):

```systemverilog
module my_mod; // GTK - Blue
```

Signal probes:

```systemverilog
logic [31:0] addr;         // GTK - Hex
logic [15:0] cnt;          // GTK - Probe, Dec
logic signed [7:0] temp;   // GTK - SDec
```

Supported colors: `Green`, `Red`, `Orange`, `Yellow`, `Blue`, `Indigo`, `Violet`.

Supported formats: `Hex`, `Dec`, `SDec`, `Bin`, `Oct`.

### File-level exclusion

Any file containing `VERILATOR_SKIP` in its first ~400 characters is skipped
during file discovery — useful for stashing tool-incompatible scratch files
in `rtl/`.

---

## Installing Verilator and GTKWave (Windows)

WSL (`wsl.exe -d Ubuntu`):

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

---

## Repository Layout

For people contributing to `auto_verilator` itself:

| File | Role |
|---|---|
| `av.py` | Top-level CLI dispatcher (`lint` / `sim`). |
| `lint.py` | Verilator lint runner. |
| `simulate.py` | Verilator build + run orchestration, probe/view resolution, GTKWave launching. |
| `sim_harness.py` | C++ harness templates and trace-format constants. |
| `filelist.py` | RTL discovery and `verilator.f` generation. |
| `gtkwave_probe.py` | Verilator JSON export parsing and `.gtkw` view writing for `--probe`. |
| `project_context.py` | `.conf` parsing and runtime path resolution. |
| `file_utils.py` | Small path helpers shared by the other modules. |

## Known Considerations

- **Single config file per scripts directory.** If multiple `*.conf` files
  exist and none is named `av.conf`, pass `--conf <name.conf>` explicitly.
- **`--probe` invokes Verilator a second time** (`--json-only-output`) to
  build the module tree. Expect the probe step to take roughly as long as
  one lint pass.
- **`--fast` / `--trace-format none` is incompatible with GTKWave and
  `--probe`.** Those options are silently ignored in no-waveform mode.
- **VCD files are large.** Prefer `fst` unless you specifically need VCD
  for downstream tooling.
- **Timing-based testbenches.** The generated harness uses
  `eventsPending` / `nextTimeSlot`, so testbenches using `--timing`
  (`always #N clk = ~clk;`, `@(posedge clk)`, etc.) advance to the next
  scheduled event rather than ticking unit-time, keeping trace files
  compact and runs fast.
