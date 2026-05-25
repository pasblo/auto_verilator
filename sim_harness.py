"""Verilator C++ simulation harness templates.

Generates ``sim_main.cpp`` for a given testbench top, parameterised by the
selected trace format. The eval loop uses Verilator's timing scheduler
(``eventsPending`` / ``nextTimeSlot``) so testbenches that drive the clock
with ``always #5 clk = ~clk;`` or block on ``@(posedge clk)`` advance in
time-jumps, not unit-time ticks.
"""

from __future__ import annotations

from pathlib import Path


TRACE_FORMAT_NONE = "none"
TRACE_FORMAT_FST  = "fst"
TRACE_FORMAT_VCD  = "vcd"
TRACE_FORMATS     = (TRACE_FORMAT_NONE, TRACE_FORMAT_FST, TRACE_FORMAT_VCD)


def default_wave_file(trace_format: str) -> str:
    if trace_format == TRACE_FORMAT_VCD:
        return "wave.vcd"
    return "wave.fst"


def trace_flag(trace_format: str) -> tuple[str, ...]:
    """Verilator CLI flag(s) to enable trace dumping for the chosen format."""
    if trace_format == TRACE_FORMAT_NONE:
        return ()
    if trace_format == TRACE_FORMAT_VCD:
        return ("--trace",)
    return ("--trace-fst",)


def generate_main_cpp(
    tb_mod_name: str,
    output_path: Path,
    wave_file: str,
    max_cycles: int,
    trace_format: str = TRACE_FORMAT_FST,
) -> None:
    tb_class = "V" + tb_mod_name
    if trace_format == TRACE_FORMAT_NONE:
        code = _NO_TRACE_TEMPLATE.format(tb_class=tb_class, max_cycles=max_cycles)
    elif trace_format == TRACE_FORMAT_VCD:
        code = _VCD_TEMPLATE.format(tb_class=tb_class, wave_file=wave_file, max_cycles=max_cycles)
    else:
        code = _FST_TEMPLATE.format(tb_class=tb_class, wave_file=wave_file, max_cycles=max_cycles)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(code, encoding="utf-8")


_NO_TRACE_TEMPLATE = """// Verilator simulation harness (auto-generated, trace-format=none)
#include "verilated.h"
#include "{tb_class}.h"

vluint64_t main_time = 0;
double sc_time_stamp() {{
    return main_time;
}}

int main(int argc, char** argv) {{
    Verilated::commandArgs(argc, argv);
    {tb_class}* top = new {tb_class};

    const vluint64_t max_time = {max_cycles};
    while (!Verilated::gotFinish() && main_time < max_time) {{
        top->eval();
        main_time++;
    }}

    top->final();
    delete top;
    return 0;
}}
"""


_VCD_TEMPLATE = """// Verilator simulation harness (auto-generated, trace-format=vcd)
#include "verilated.h"
#include "{tb_class}.h"
#include "verilated_vcd_c.h"

vluint64_t main_time = 0;
double sc_time_stamp() {{
    return main_time;
}}

int main(int argc, char** argv) {{
    Verilated::commandArgs(argc, argv);
    {tb_class}* top = new {tb_class};

    Verilated::traceEverOn(true);
    VerilatedVcdC* tfp = new VerilatedVcdC;
    top->trace(tfp, 99);
    tfp->open("{wave_file}");

    const vluint64_t max_time = {max_cycles};
    while (!Verilated::gotFinish() && main_time < max_time) {{
        top->eval();
        tfp->dump(main_time);
        if (top->eventsPending()) {{
            vluint64_t next = top->nextTimeSlot();
            main_time = (next > main_time) ? next : main_time + 1;
        }} else {{
            main_time++;
        }}
    }}

    top->final();
    tfp->close();
    delete tfp;
    delete top;
    return 0;
}}
"""


_FST_TEMPLATE = """// Verilator simulation harness (auto-generated, trace-format=fst)
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
        if (top->eventsPending()) {{
            vluint64_t next = top->nextTimeSlot();
            main_time = (next > main_time) ? next : main_time + 1;
        }} else {{
            main_time++;
        }}
    }}

    top->final();
    tfp->close();
    delete tfp;
    delete top;
    return 0;
}}
"""
