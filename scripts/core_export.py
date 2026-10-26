__copyright__ = "Copyright (c) 2026 Alex Laird"
__license__ = "MIT"

import argparse
import ast
import json
import re
import shutil
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "custom_components" / "hearth"
TESTS = ROOT / "tests"

#: Each module's docstring in Home Assistant core, which requires one (this repo's own modules have none).
MODULE_DOCSTRINGS = {
    "__init__.py": "The Hearth integration.",
    "config_flow.py": "Config flow for the Hearth integration.",
    "client.py": "The Hearth integration's connection to Hearth.",
    "const.py": "Constants for the Hearth integration.",
    "coordinator.py": "The Hearth integration's coordinator: the minute sync with Hearth.",
    "diagnostics.py": "Diagnostics for the Hearth integration.",
    "exception.py": "Exceptions for the Hearth integration.",
    "sensor.py": "The Hearth integration's self-check sensors.",
    "sync.py": "What the Hearth integration posts, and how it applies Hearth's settings.",
    "tests/__init__.py": "Tests for the Hearth integration.",
    "tests/conftest.py": "Fixtures for the Hearth integration's tests.",
    "tests/testcase.py": "Shared setup for the Hearth integration's tests.",
    "tests/fakethermostat.py": "A thermostat for the Hearth integration's tests.",
    "tests/test_config_flow.py": "Tests for the Hearth integration's config flow.",
    "tests/test_init.py": "Tests for setting up the Hearth integration.",
    "tests/test_sync.py": "Tests for the Hearth integration's sync.",
}

#: Applying a setting catches any failure on purpose: thermostat integrations raise whatever they like.
APPLY_ANY_FAILURE = "# noqa: BLE001"

#: Core's helper for starting a reconfigure flow can't ask for advanced options, which the API address step needs.
ADVANCED_RECONFIGURE = "# pylint: disable=home-assistant-test-flow-start-helper"

#: Climate's entity component isn't exported from its root, so it's imported from climate.const.
CLIMATE_COMPONENT = "# pylint: disable=home-assistant-component-root-import"

#: Left out of core: HACS's own files, the brand images (core's are in home-assistant/brands) and the generated
#: translations (core builds them from strings.json).
SKIPPED = {"brand", "translations", "__pycache__"}


def export(core: Path) -> None:
    """
    Write the integration and its tests into a Home Assistant core checkout, in core's layout and conventions.

    :param core: The core checkout's root.
    """
    integration = core / "homeassistant" / "components" / "hearth"
    tests = core / "tests" / "components" / "hearth"
    for target in (integration, tests):
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True)

    for path in sorted(SOURCE.iterdir()):
        if path.name in SKIPPED:
            continue
        elif path.name == "manifest.json":
            (integration / path.name).write_text(_core_manifest(path))
        elif path.suffix == ".py":
            text = _percent_logging(_probatio(_climate_root(_relative_imports(path.read_text()))))
            if path.name == "__init__.py":
                text = _entry_setup_returns_none(text)
            if path.name == "coordinator.py":
                text = text.replace("except Exception as e:\n", f"except Exception as e:  {APPLY_ANY_FAILURE}\n")
            (integration / path.name).write_text(_core_module(text, MODULE_DOCSTRINGS[path.name]))
        else:
            shutil.copy(path, integration / path.name)

    for path in sorted(TESTS.glob("*.py")):
        docstring = MODULE_DOCSTRINGS[f"tests/{path.name}"]
        text = _core_tests(path.read_text())
        if path.name == "conftest.py":
            text = _without_custom_integrations_fixture(text)
        if path.name == "fakethermostat.py":
            text = _native_climate_attributes(text)
        (tests / path.name).write_text(_core_module(text, docstring))


def _core_manifest(path: Path) -> str:
    manifest = json.loads(path.read_text())
    for key in ("version", "issue_tracker"):
        manifest.pop(key, None)
    manifest["documentation"] = "https://www.home-assistant.io/integrations/hearth"
    manifest["categories"] = ["climate.thermostats_heating"]
    manifest["loggers"] = ["pyhearth"]
    manifest["quality_scale"] = "platinum"
    ordered = {"domain": manifest.pop("domain"), "name": manifest.pop("name")}
    ordered.update(dict(sorted(manifest.items())))
    return json.dumps(ordered, indent=2) + "\n"


def _core_module(text: str, docstring: str) -> str:
    text = re.sub(r'\A__copyright__ = "[^"]*"\n__license__ = "[^"]*"\n\n?', "", text)
    return f'"""{docstring}"""\n\n{_summary_on_first_line(_named_docstrings(text))}'


def _probatio(text: str) -> str:
    """
    Core validates with probatio, voluptuous's successor there (not in a released Home Assistant yet, so this repo
    keeps voluptuous for the versions it supports).
    """
    text = text.replace("import voluptuous as vol\n", "import probatio\n")
    return re.sub(r"\bvol\.", "probatio.", text)


def _percent_logging(text: str) -> str:
    """
    Log calls with ``%s`` arguments, as core's ruff rules want, instead of this repo's f-strings.
    """
    edits: list[tuple[ast.expr, str]] = []
    for node in ast.walk(ast.parse(text)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "logger"
                and node.args and isinstance(node.args[0], ast.JoinedStr)):
            continue
        message, values = "", list[str]()
        for part in node.args[0].values:
            if isinstance(part, ast.Constant):
                message += str(part.value).replace("%", "%%")
            elif isinstance(part, ast.FormattedValue):
                message += "%r" if part.conversion == ord("r") else "%s"
                values.append(ast.get_source_segment(text, part.value) or "")
        edits.append((node.args[0], ", ".join([json.dumps(message), *values])))
    return _replace_nodes(text, edits)


def _named_docstrings(text: str) -> str:
    """
    A docstring for each public class and function that has none, from its name, as core's ruff rules want (this
    repo documents what needs it and names its tests to read as sentences).
    """
    lines = text.split("\n")
    inserts = []
    for node in ast.walk(ast.parse(text)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) or ast.get_docstring(node):
            continue
        if node.name.startswith("_") and node.name != "__init__":
            continue
        first = node.body[0]
        at = first.lineno - 1
        while at > node.lineno and (not lines[at - 1].strip() or lines[at - 1].strip().startswith("#")):
            at -= 1
        inserts.append((at, f'{" " * first.col_offset}"""{_described(node)}"""'))
    for index, line in sorted(inserts, reverse=True):
        lines.insert(index, line)
    return "\n".join(lines)


def _described(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> str:
    if node.name == "__init__":
        return "Initialize the instance."
    words = re.sub(r"(?<!^)(?=[A-Z])", " ", node.name).replace("_", " ").lower().split()
    if isinstance(node, ast.ClassDef) and words[0] == "test":
        return f"Tests for {' '.join(words[1:])}."
    sentence = " ".join(words)
    return sentence[0].upper() + sentence[1:] + "."


def _replace_nodes(text: str, edits: Sequence[tuple[ast.expr, str]]) -> str:
    lines = text.split("\n")
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line) + 1)

    def offset(line: int, column: int) -> int:
        return starts[line - 1] + len(lines[line - 1].encode()[:column].decode())

    for node, replacement in sorted(edits, key=lambda edit: (edit[0].lineno, edit[0].col_offset), reverse=True):
        begin = offset(node.lineno, node.col_offset)
        end = offset(node.end_lineno or node.lineno, node.end_col_offset or node.col_offset)
        text = text[:begin] + replacement + text[end:]
    return text


def _entry_setup_returns_none(text: str) -> str:
    """
    Setting up and unloading an entry returns nothing in core (raising on failure); released Home Assistant still
    expects ``True``.
    """
    text = re.sub(r"(async def async_(?:setup|unload)_entry\([^)]*\)) -> bool:", r"\1 -> None:", text)
    text = re.sub(r"\n    :return: ``True`` once it's (?:set up|unloaded)\.", "", text)
    forward = "    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)\n"
    text = text.replace(f"{forward}    return True\n", forward)
    return text.replace("    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)",
                        "    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)")


def _climate_root(text: str) -> str:
    """
    Climate's constants from the component root, as core's pylint wants; released Home Assistant doesn't export them
    there yet, so this repo imports them from ``climate.const``.
    """
    text = text.replace("homeassistant.components.climate.const import", "homeassistant.components.climate import")
    # The one climate name core doesn't re-export from its root: climate's own entity component (an open review
    # question: the step's native unit is read from the thermostat's entity).
    return re.sub(r"from homeassistant\.components\.climate import DATA_COMPONENT(.*)\n",
                  rf"from homeassistant.components.climate.const import (  {CLIMATE_COMPONENT}\n"
                  r"    DATA_COMPONENT\1,\n)\n",
                  text)


def _relative_imports(text: str) -> str:
    text = re.sub(r"\bfrom custom_components\.hearth\.(\w+) import", r"from .\1 import", text)
    return re.sub(r"\bfrom custom_components\.hearth import", "from . import", text)


def _summary_on_first_line(text: str) -> str:
    """
    Docstrings with the summary on the opening line, as core's ruff rules want (this repo puts the quotes on their
    own line).
    """
    lines = text.split("\n")
    openings = sorted({node.body[0].lineno - 1
                       for node in ast.walk(ast.parse(text))
                       if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                       and ast.get_docstring(node, clean=False) is not None}, reverse=True)
    for index in openings:
        if lines[index].strip() == '"""':
            lines[index] = lines[index] + lines[index + 1].strip()
            del lines[index + 1]
    return "\n".join(lines)


def _core_tests(text: str) -> str:
    text = _climate_root(text.replace("pytest_homeassistant_custom_component.", "pytest_homeassistant."))
    text = text.replace("custom_components.hearth", "homeassistant.components.hearth")
    reconfigure = 'hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_RECONFIGURE,'
    text = text.replace(f"flow = await {reconfigure}",
                        f"flow = await hass.config_entries.flow.async_init(  {ADVANCED_RECONFIGURE}\n"
                        '            DOMAIN, context={"source": SOURCE_RECONFIGURE,')
    return re.sub(r"\bfrom tests\.(testcase|fakethermostat) import", r"from .\1 import", text)


def _native_climate_attributes(text: str) -> str:
    """
    The test thermostat with climate's ``native_`` attributes, which core has and released Home Assistant doesn't yet.
    """
    renamed = r"\b_attr_(target_temperature(?!_step)\w*|current_temperature|temperature_unit)\b"
    return re.sub(renamed, r"_attr_native_\1", text)


def _without_custom_integrations_fixture(text: str) -> str:
    return re.sub(r"\n*@pytest\.fixture\(autouse=True\)\ndef auto_enable_custom_integrations\([^)]*\)[^\n]*\n"
                  r"    return\n", "\n", text)


def main() -> None:
    """
    Export to the core checkout given on the command line.
    """
    parser = argparse.ArgumentParser(description="Write ha-hearth into a Home Assistant core checkout.")
    parser.add_argument("core", type=Path, help="The Home Assistant core checkout.")
    export(parser.parse_args().core.resolve())


if __name__ == "__main__":
    main()
