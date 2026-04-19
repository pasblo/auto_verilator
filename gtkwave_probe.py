import json
import os
import re
import subprocess
from datetime import datetime

TRACE_FLAG_RJUSTIFY = 1 << 5
TRACE_FLAG_HEX = 1 << 1
TRACE_FLAG_DEC = 1 << 2
TRACE_FLAG_BIN = 1 << 3
TRACE_FLAG_OCT = 1 << 4
TRACE_FLAG_SIGNED = 1 << 10

COLOR_INDEX = {
    "RED": 1,
    "ORANGE": 2,
    "YELLOW": 3,
    "GREEN": 4,
    "BLUE": 5,
    "INDIGO": 6,
    "VIOLET": 7,
}

MODULE_COLOR_RE = re.compile(r"//\s*GTK\s*-\s*(Green|Red|Orange|Yellow|Blue|Indigo|Violet)\b", re.IGNORECASE)
PROBE_RE = re.compile(r"//\s*GTK\s*-\s*(?:Probe\s*,\s*)?(Hex|Dec|SDec|Bin|Oct)\b", re.IGNORECASE)
MODULE_DEF_RE = re.compile(r"\bmodule\s+(?:automatic\s+)?([A-Za-z_][A-Za-z0-9_$]*)\b")
INTERFACE_DEF_RE = re.compile(r"\binterface\s+(?:automatic\s+)?([A-Za-z_][A-Za-z0-9_$]*)\b")
ENDMODULE_RE = re.compile(r"\bendmodule\b")
ENDINTERFACE_RE = re.compile(r"\bendinterface\b")


def update_gtkwave_view_from_sv(
    sim_dir,
    views_dir,
    wave_file,
    view_file,
    vlt_path,
    tb_path,
    tb_mod_name,
    filelist_path,
    fresh=False,
):
    tree, meta = _run_verilator_json(sim_dir, vlt_path, filelist_path, tb_path, tb_mod_name)
    file_id_to_path = _file_id_map(meta)
    module_color_lines, probe_lines, probe_line_names, module_color_by_name, probe_entries_by_module = _parse_comment_lines(meta)
    dtype_ranges = _build_dtype_ranges(tree)
    modules = _build_modules(tree, dtype_ranges)
    _apply_module_colors(modules, file_id_to_path, module_color_lines, module_color_by_name)
    _apply_probe_formats(modules, file_id_to_path, probe_lines, probe_line_names, probe_entries_by_module)
    signal_specs = _build_signal_specs(modules, tb_mod_name)

    view_path = view_file if os.path.isabs(view_file) else os.path.join(views_dir, view_file)
    wave_path = wave_file if os.path.isabs(wave_file) else os.path.join(sim_dir, wave_file)
    added_specs = _write_gtkwave_view(view_path, wave_path, signal_specs, fresh=fresh)
    return {
        "all": signal_specs,
        "added": added_specs,
        "view_path": view_path,
    }


def _run_verilator_json(sim_dir, vlt_path, filelist_path, tb_path, tb_mod_name):
    tree_path = os.path.join(sim_dir, "verilator.tree.json")
    meta_path = os.path.join(sim_dir, "verilator.tree.meta.json")
    cmd = [
        "verilator",
        "-sv",
        "-Wall",
        "--bbox-sys",
        "--bbox-unsup",
        str(vlt_path),
        "--json-only-output",
        tree_path,
        "--json-only-meta-output",
        meta_path,
        "-f",
        str(filelist_path),
        "--top-module",
        tb_mod_name,
        str(tb_path),
    ]
    result = subprocess.run(cmd, cwd=sim_dir, capture_output=True, text=True)
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        raise RuntimeError(f"Verilator JSON export failed with exit code {result.returncode}")
    with open(tree_path, "r", encoding="utf-8") as f:
        tree = json.load(f)
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return tree, meta


def _file_id_map(meta):
    file_id_to_path = {}
    for file_id, info in meta.get("files", {}).items():
        path = info.get("realpath") or info.get("filename")
        if not path:
            continue
        file_id_to_path[file_id] = os.path.abspath(path)
    return file_id_to_path


def _parse_comment_lines(meta):
    module_color_lines = {}
    probe_lines = {}
    probe_line_names = {}
    module_color_by_name = {}
    probe_entries_by_module = {}
    for file_id, info in meta.get("files", {}).items():
        path = info.get("realpath") or info.get("filename")
        if not path or path.startswith("<"):
            continue
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            continue
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                current_module = None
                for idx, line in enumerate(f, 1):
                    code_part, _, _ = line.partition("//")
                    if ENDMODULE_RE.search(code_part) or ENDINTERFACE_RE.search(code_part):
                        current_module = None
                    module_match = MODULE_DEF_RE.search(code_part)
                    interface_match = INTERFACE_DEF_RE.search(code_part)
                    if module_match:
                        current_module = module_match.group(1)
                    elif interface_match:
                        current_module = interface_match.group(1)
                    color_match = MODULE_COLOR_RE.search(line)
                    if color_match:
                        module_color_lines[(abs_path, idx)] = color_match.group(1).upper()
                        if current_module:
                            module_color_by_name[current_module] = color_match.group(1).upper()
                    probe_match = PROBE_RE.search(line)
                    if probe_match:
                        probe_lines[(abs_path, idx)] = probe_match.group(1).upper()
                        names = _extract_signal_names_from_line(line)
                        probe_line_names[(abs_path, idx)] = names
                        if current_module:
                            probe_entries_by_module.setdefault(current_module, [])
                            for name in names:
                                probe_entries_by_module[current_module].append({
                                    "name": name,
                                    "format": probe_match.group(1).upper(),
                                })
        except OSError:
            continue
    return module_color_lines, probe_lines, probe_line_names, module_color_by_name, probe_entries_by_module


def _extract_signal_names_from_line(line):
    line = line.split("//", 1)[0]
    if not line.strip():
        return []
    line = line.split("=", 1)[0]
    line = re.sub(r"\[[^\]]*\]", " ", line)
    line = line.replace(";", " ")
    names = []
    for part in line.split(","):
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_$]*", part)
        if not tokens:
            continue
        name = tokens[-1]
        if name in {"module", "input", "output", "inout", "logic", "wire", "reg", "var", "signed", "unsigned"}:
            continue
        names.append(name)
    return names


def _build_modules(tree, dtype_ranges):
    modules = {}
    for mod in tree.get("modulesp", []):
        vars_info, cells_info = _collect_module_items(mod, dtype_ranges)
        modules[mod.get("addr")] = {
            "name": mod.get("name"),
            "origName": mod.get("origName", mod.get("name")),
            "addr": mod.get("addr"),
            "loc": mod.get("loc"),
            "vars": vars_info,
            "cells": cells_info,
            "color": None,
            "probe_vars": [],
        }
    return modules


def _collect_module_items(module_node, dtype_ranges):
    vars_info = []
    cells_info = []

    def walk(node, scope):
        if not isinstance(node, dict):
            return
        ntype = node.get("type")
        if ntype == "VAR":
            vars_info.append({
                "name": node.get("name"),
                "loc": node.get("loc"),
                "scope": scope[:],
                "range": dtype_ranges.get(node.get("dtypep")),
            })
            return
        if ntype == "CELL":
            cells_info.append({
                "name": node.get("name"),
                "modp": node.get("modp"),
                "loc": node.get("loc"),
                "scope": scope[:],
            })
            return
        if ntype == "GENBLOCK":
            scope_name = node.get("name")
            new_scope = scope + ([scope_name] if scope_name else [])
            for child in node.get("itemsp", []):
                walk(child, new_scope)
            return

        for value in node.values():
            if isinstance(value, list):
                for child in value:
                    if isinstance(child, dict):
                        walk(child, scope)

    for stmt in module_node.get("stmtsp", []):
        walk(stmt, [])
    return vars_info, cells_info


def _build_dtype_ranges(tree):
    ranges = {}
    for misc in tree.get("miscsp", []):
        if misc.get("type") != "TYPETABLE":
            continue
        for dtype in misc.get("typesp", []):
            addr = dtype.get("addr")
            if not addr:
                continue
            range_str = dtype.get("range") or dtype.get("declRange")
            if not range_str:
                continue
            range_str = range_str.strip()
            if range_str.startswith("[") and range_str.endswith("]"):
                range_str = range_str[1:-1].strip()
            ranges[addr] = range_str
    return ranges


def _apply_module_colors(modules, file_id_to_path, module_color_lines, module_color_by_name):
    for mod in modules.values():
        name_color = module_color_by_name.get(mod.get("name")) or module_color_by_name.get(mod.get("origName"))
        if name_color:
            mod["color"] = name_color
            continue
        loc = mod.get("loc")
        parsed = _parse_loc(loc)
        if not parsed:
            continue
        file_id, start_line, end_line = parsed
        path = file_id_to_path.get(file_id)
        if not path:
            continue
        for line_no in range(start_line, end_line + 1):
            color = module_color_lines.get((path, line_no))
            if color:
                mod["color"] = color
                break


def _apply_probe_formats(modules, file_id_to_path, probe_lines, probe_line_names, probe_entries_by_module):
    for mod in modules.values():
        probe_names = {probe["name"] for probe in mod["probe_vars"]}
        for var in mod["vars"]:
            loc = var.get("loc")
            parsed = _parse_loc(loc)
            if not parsed:
                continue
            file_id, start_line, end_line = parsed
            path = file_id_to_path.get(file_id)
            if not path:
                continue
            fmt = None
            for line_no in range(start_line, end_line + 1):
                fmt = probe_lines.get((path, line_no))
                if fmt:
                    break
            if fmt:
                mod["probe_vars"].append({
                    "name": var.get("name"),
                    "scope": var.get("scope", []),
                    "range": var.get("range"),
                    "format": fmt,
                })
                probe_names.add(var.get("name"))

        entries = probe_entries_by_module.get(mod.get("name")) or probe_entries_by_module.get(mod.get("origName")) or []
        for entry in entries:
            name = entry.get("name")
            if not name or name in probe_names:
                continue
            mod["probe_vars"].append({
                "name": name,
                "scope": [],
                "range": None,
                "format": entry.get("format", "HEX"),
            })
            probe_names.add(name)

        loc = mod.get("loc")
        parsed = _parse_loc(loc)
        if not parsed:
            continue
        file_id, start_line, end_line = parsed
        path = file_id_to_path.get(file_id)
        if not path:
            continue
        for line_no in range(start_line, end_line + 1):
            fmt = probe_lines.get((path, line_no))
            if not fmt:
                continue
            names = probe_line_names.get((path, line_no), [])
            for name in names:
                if name in probe_names:
                    continue
                mod["probe_vars"].append({
                    "name": name,
                    "scope": [],
                    "range": None,
                    "format": fmt,
                })
                probe_names.add(name)


def _build_signal_specs(modules, tb_mod_name):
    top_module = _find_top_module(modules, tb_mod_name)
    if not top_module:
        raise RuntimeError(f"Top module '{tb_mod_name}' not found in Verilator JSON output.")

    signal_specs = []
    seen = set()

    def walk_module(mod, inst_path, inherited_color):
        module_color = mod.get("color") or inherited_color
        for probe in mod.get("probe_vars", []):
            local_path = probe.get("scope", [])
            full_path = inst_path
            if local_path:
                full_path += "." + ".".join(local_path)
            full_path += "." + probe["name"]
            range_str = probe.get("range")
            if range_str and ":" in range_str:
                full_path += f"[{range_str}]"
            if full_path not in seen:
                seen.add(full_path)
                signal_specs.append({
                    "path": full_path,
                    "format": probe["format"],
                    "color": module_color,
                })

        for cell in mod.get("cells", []):
            child = modules.get(cell.get("modp"))
            if not child:
                continue
            scope = cell.get("scope", [])
            path = inst_path
            if scope:
                path += "." + ".".join(scope)
            path += "." + cell.get("name")
            walk_module(child, path, module_color)

    walk_module(top_module, f"TOP.{tb_mod_name}", None)
    return signal_specs


def _find_top_module(modules, tb_mod_name):
    for mod in modules.values():
        if mod.get("name") == tb_mod_name or mod.get("origName") == tb_mod_name:
            return mod
    return None


def _write_gtkwave_view(view_path, wave_path, signal_specs, fresh=False):
    os.makedirs(os.path.dirname(view_path), exist_ok=True)
    existing_lines = []
    existing_signals = set()
    view_exists = os.path.exists(view_path)
    if view_exists and not fresh:
        with open(view_path, "r", encoding="utf-8") as f:
            existing_lines = f.read().splitlines()
        existing_signals = _extract_signals(existing_lines)
        existing_lines = _update_header(existing_lines, wave_path, view_path)
    else:
        existing_lines = _build_header(wave_path, view_path)

    new_lines = []
    added_specs = []
    for spec in signal_specs:
        if spec["path"] in existing_signals:
            continue
        added_specs.append(spec)
        flags = _format_to_flags(spec["format"])
        new_lines.append(f"@{flags}")
        if spec["color"]:
            color_index = COLOR_INDEX.get(spec["color"], 0)
            new_lines.append(f"[color] {color_index}")
        new_lines.append(spec["path"])

    if not new_lines and view_exists and not fresh:
        return added_specs
    with open(view_path, "w", encoding="utf-8") as f:
        f.write("\n".join(existing_lines + new_lines) + "\n")
    return added_specs


def _extract_signals(lines):
    signals = set()
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped[0] in ["[", "@", "*", "#", "-"]:
            continue
        signals.add(stripped)
    return signals


def _update_header(lines, wave_path, view_path):
    updated = []
    saw_dumpfile = False
    saw_savefile = False
    for line in lines:
        if line.startswith("[dumpfile]"):
            updated.append(f"[dumpfile] \"{wave_path}\"")
            saw_dumpfile = True
        elif line.startswith("[savefile]"):
            updated.append(f"[savefile] \"{view_path}\"")
            saw_savefile = True
        else:
            updated.append(line)
    if not saw_dumpfile:
        updated.insert(0, f"[dumpfile] \"{wave_path}\"")
    if not saw_savefile:
        insert_at = 1 if updated and updated[0].startswith("[dumpfile]") else 0
        updated.insert(insert_at, f"[savefile] \"{view_path}\"")
    return updated


def _build_header(wave_path, view_path):
    now = datetime.now().strftime("%a %b %d %H:%M:%S %Y")
    return [
        "[*]",
        "[*] GTKWave savefile generated by auto_verilator",
        f"[*] {now}",
        "[*]",
        f"[dumpfile] \"{wave_path}\"",
        f"[savefile] \"{view_path}\"",
        "[timestart] 0",
    ]


def _format_to_flags(fmt):
    fmt = fmt.upper()
    if fmt == "HEX":
        flags = TRACE_FLAG_RJUSTIFY | TRACE_FLAG_HEX
    elif fmt == "DEC":
        flags = TRACE_FLAG_RJUSTIFY | TRACE_FLAG_DEC
    elif fmt == "SDEC":
        flags = TRACE_FLAG_RJUSTIFY | TRACE_FLAG_DEC | TRACE_FLAG_SIGNED
    elif fmt == "BIN":
        flags = TRACE_FLAG_RJUSTIFY | TRACE_FLAG_BIN
    elif fmt == "OCT":
        flags = TRACE_FLAG_RJUSTIFY | TRACE_FLAG_OCT
    else:
        flags = TRACE_FLAG_RJUSTIFY | TRACE_FLAG_HEX
    return format(flags, "x")


def _parse_loc(loc):
    if not loc:
        return None
    parts = loc.split(",")
    if len(parts) < 3:
        return None
    file_id = parts[0]
    try:
        start_line = int(parts[1].split(":")[0])
        end_line = int(parts[2].split(":")[0])
    except ValueError:
        return None
    return file_id, start_line, end_line
