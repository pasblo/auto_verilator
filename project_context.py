from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Dict


DEFAULT_HDL_EXTENSIONS = ("sv",)
DEFAULT_EXCLUDE_FOLDERS = ("tests",)
DEFAULT_EXCLUDE_TESTBENCHES = "true"
DEFAULT_FOLDER_ORDER = ("constants", "interfaces", "interstage", "components")
DEFAULT_SIM_MAX_CYCLES = 9_999_999
DEFAULT_FILELIST_FLAGS = (
    "-Wall",
    "-Wno-fatal",
    "-j 0",
    "--assert",
    "--no-trace-top",
    "--trace-structs",
    "--timing",
    "--x-initial unique",
)

_SECTION_RE = re.compile(r"^\[(?P<name>[^\]]+)\]\s*$")
_KV_RE = re.compile(r"^(?P<key>[A-Za-z0-9_.-]+)\s*(=|:)\s*(?P<value>.*)$")


@dataclass(frozen=True)
class ConfData:
    path: Path
    sections: Dict[str, Dict[str, str]]

    def section(self, name: str) -> Dict[str, str]:
        return self.sections.get(name.lower(), {})

    def get(self, key: str, *section_order: str, default: str | None = None) -> str | None:
        normalized_key = _normalize_key(key)
        if section_order:
            candidate_sections = [section.lower() for section in section_order]
        else:
            candidate_sections = ["verilator", "paths", "settings", "tools", "default"]

        for section in candidate_sections:
            section_map = self.sections.get(section)
            if section_map and normalized_key in section_map:
                return section_map[normalized_key]
        return default


@dataclass(frozen=True)
class RuntimeConfig:
    tool_dir: Path
    scripts_dir: Path
    project_root: Path
    conf: ConfData
    rtl_dir: Path
    sim_root: Path
    sim_dir: Path
    views_dir: Path
    vlt_path: Path
    filelist_path: Path
    last_gtkwave_view_path: Path
    verilator_bin: str
    gtkwave_bin: str
    hdl_extensions: tuple[str, ...]
    exclude_folders: tuple[str, ...]
    exclude_testbenches: str
    folder_order: tuple[str, ...]
    simulation_max_cycles: int
    filelist_flags: tuple[str, ...]


def resolve_runtime_config(tool_dir: Path, conf_name: str | None = None) -> RuntimeConfig:
    tool_dir = tool_dir.resolve()
    scripts_dir = tool_dir.parent
    project_root = scripts_dir.parent

    conf_path = resolve_conf_path(scripts_dir, conf_name)
    conf = parse_conf_file(conf_path)

    rtl_dir = _resolve_path(conf.get("RTL_DIR"), scripts_dir, project_root / "rtl")
    sim_root = _resolve_path(conf.get("SIM_ROOT"), scripts_dir, project_root / "sim")
    sim_dir = _resolve_path(conf.get("SIM_DIR"), scripts_dir, sim_root / "verilator")
    views_dir = _resolve_path(conf.get("GTKWAVE_VIEWS_DIR"), scripts_dir, sim_root / "gtk_views")
    vlt_path = _resolve_path(conf.get("VERILATOR_CONF_VLT"), scripts_dir, scripts_dir / "verilator_conf.vlt")

    verilator_bin = conf.get("VERILATOR_BIN", default="verilator") or "verilator"
    gtkwave_bin = conf.get("GTKWAVE_BIN", default="gtkwave") or "gtkwave"

    hdl_extensions = _parse_extensions(conf)
    exclude_folders = _parse_csv(conf.get("EXCLUDE_FOLDERS"), DEFAULT_EXCLUDE_FOLDERS)
    exclude_testbenches = _parse_str(conf.get("EXCLUDE_TESTBENCHES"), DEFAULT_EXCLUDE_TESTBENCHES)
    folder_order = _parse_csv(conf.get("FOLDER_ORDER"), DEFAULT_FOLDER_ORDER)
    simulation_max_cycles = _parse_int(conf.get("SIMULATION_MAX_CYCLES"), DEFAULT_SIM_MAX_CYCLES)
    filelist_flags = _parse_flags(conf.get("FILELIST_FLAGS"), DEFAULT_FILELIST_FLAGS)

    filelist_path = sim_dir / "verilator.f"
    last_gtkwave_view_path = views_dir / ".last_gtkwave_view"

    return RuntimeConfig(
        tool_dir=tool_dir,
        scripts_dir=scripts_dir,
        project_root=project_root,
        conf=conf,
        rtl_dir=rtl_dir,
        sim_root=sim_root,
        sim_dir=sim_dir,
        views_dir=views_dir,
        vlt_path=vlt_path,
        filelist_path=filelist_path,
        last_gtkwave_view_path=last_gtkwave_view_path,
        verilator_bin=verilator_bin,
        gtkwave_bin=gtkwave_bin,
        hdl_extensions=tuple(hdl_extensions),
        exclude_folders=tuple(exclude_folders),
        exclude_testbenches=exclude_testbenches,
        folder_order=tuple(folder_order),
        simulation_max_cycles=simulation_max_cycles,
        filelist_flags=tuple(filelist_flags),
    )


def resolve_conf_path(scripts_dir: Path, conf_name: str | None) -> Path:
    if conf_name:
        conf_path = Path(conf_name)
        if not conf_path.is_absolute():
            conf_path = scripts_dir / conf_path
        conf_path = conf_path.resolve()
        if not conf_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {conf_path}")
        return conf_path

    default_conf = (scripts_dir / "av.conf").resolve()
    if default_conf.exists():
        return default_conf

    conf_files = sorted(path.resolve() for path in scripts_dir.glob("*.conf"))
    if len(conf_files) == 1:
        return conf_files[0]

    if not conf_files:
        raise FileNotFoundError(
            f"No .conf file found in scripts directory: {scripts_dir}\n"
            "Expected something like scripts/av.conf."
        )

    joined = ", ".join(path.name for path in conf_files)
    raise FileNotFoundError(
        f"Multiple .conf files found in {scripts_dir}: {joined}\n"
        "Pass one explicitly with --conf <name.conf>."
    )


def parse_conf_file(conf_path: Path) -> ConfData:
    sections: Dict[str, Dict[str, str]] = {"default": {}}
    current_section = "default"

    with conf_path.open("r", encoding="utf-8") as conf_file:
        for raw_line in conf_file:
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith(";") or stripped.startswith("//"):
                continue

            section_match = _SECTION_RE.match(stripped)
            if section_match:
                current_section = section_match.group("name").strip().lower()
                sections.setdefault(current_section, {})
                continue

            kv_match = _KV_RE.match(stripped)
            if not kv_match:
                continue

            key = _normalize_key(kv_match.group("key"))
            value = _strip_inline_comment(kv_match.group("value").strip())
            sections[current_section][key] = value

    return ConfData(path=conf_path, sections=sections)


def _parse_extensions(conf: ConfData) -> list[str]:
    raw = conf.get("HDL_EXTENSIONS")

    if raw is None:
        return list(DEFAULT_HDL_EXTENSIONS)

    extensions = [part.strip().lstrip(".").lower() for part in raw.split(",") if part.strip()]
    return extensions or list(DEFAULT_HDL_EXTENSIONS)


def _parse_csv(raw_value: str | None, default_values: tuple[str, ...]) -> list[str]:
    if raw_value is None:
        return list(default_values)
    values = [part.strip() for part in raw_value.split(",") if part.strip()]
    return values or list(default_values)


def _parse_str(raw_value: str | None, default_values: tuple[str, ...]) -> str:
    if raw_value is None:
        return default_values
    return raw_value


def _parse_flags(raw_value: str | None, default_values: tuple[str, ...]) -> list[str]:
    if raw_value is None:
        return list(default_values)
    delimiter = ";" if ";" in raw_value else ","
    values = [part.strip() for part in raw_value.split(delimiter) if part.strip()]
    return values or list(default_values)


def _parse_int(raw_value: str | None, default_value: int) -> int:
    if raw_value is None:
        return default_value
    try:
        return int(raw_value, 0)
    except ValueError:
        return default_value


def _resolve_path(raw_value: str | None, base_dir: Path, default_path: Path) -> Path:
    if raw_value is None:
        return default_path.resolve()

    parsed = Path(raw_value)
    if not parsed.is_absolute():
        parsed = base_dir / parsed
    return parsed.resolve()


def _normalize_key(key: str) -> str:
    return key.strip().replace("-", "_").replace(".", "_").upper()


def _strip_inline_comment(value: str) -> str:
    in_single = False
    in_double = False
    i = 0
    kept = []
    while i < len(value):
        char = value[i]

        if char == "'" and not in_double:
            in_single = not in_single
            kept.append(char)
            i += 1
            continue

        if char == '"' and not in_single:
            in_double = not in_double
            kept.append(char)
            i += 1
            continue

        if not in_single and not in_double and value.startswith("//", i):
            break
        if not in_single and not in_double and char == "#":
            break

        kept.append(char)
        i += 1

    return "".join(kept).strip()
