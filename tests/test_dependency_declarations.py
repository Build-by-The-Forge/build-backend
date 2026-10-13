"""Dependency declarations cannot drift (backend hardening C4).

requirements.txt (runtime) and requirements-dev.txt (tooling) are the only
dependency declaration: exact pins for the full closure, with environment
markers where a platform needs something different. These tests run in the
environment CI installs from those files, so they also catch an environment
that resolved differently from the pins.
"""

import ast
import re
import sys
import tomllib
from importlib.metadata import PackageNotFoundError, distribution, packages_distributions
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILE = ROOT / "requirements.txt"
DEV_FILE = ROOT / "requirements-dev.txt"
LOCAL_PACKAGES = {"app", "scripts", "tests", "pg_smoke", "boundary"}
DEV_TOOLS = {
    "pytest",
    "pytest-asyncio",
    "pytest-cov",
    "pytest-env",
    "ruff",
    "mypy",
    "pre-commit",
    "coverage",
    "respx",
    "aiosqlite",
}
PIN_LINE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[a-z0-9,]+\])?==(?P<version>[^\s;]+)(?:\s*;\s*(?P<marker>.+))?$"
)
PLATFORMS = {
    "linux": {"sys_platform": "linux", "platform_system": "Linux", "os_name": "posix"},
    "win32": {"sys_platform": "win32", "platform_system": "Windows", "os_name": "nt"},
}


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def requirement_lines(path: Path) -> list[str]:
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.startswith("-r "):
            lines += requirement_lines(path.parent / line[3:].strip())
        elif line:
            lines.append(line)
    return lines


def pins(path: Path, platform: str | None = None) -> dict[str, Requirement]:
    """name -> Requirement for the lines whose marker holds on `platform`
    (the running platform by default)."""
    env = default_environment()
    if platform:
        env |= PLATFORMS[platform]
    out = {}
    for line in requirement_lines(path):
        req = Requirement(line)
        if req.marker is None or req.marker.evaluate(env):
            out[norm(req.name)] = req
    return out


def pinned_version(req: Requirement) -> str:
    (spec,) = req.specifier
    return spec.version


def test_every_requirement_is_an_exact_pin():
    for path in (RUNTIME_FILE, DEV_FILE):
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line or line == "-r requirements.txt" and path == DEV_FILE:
                continue
            assert PIN_LINE.match(line), f"{path.name}: not an exact pin: {line!r}"


def test_each_package_is_pinned_once_per_platform():
    for platform in PLATFORMS:
        names = [
            norm(Requirement(line).name)
            for line in requirement_lines(DEV_FILE)
            if Requirement(line).marker is None or Requirement(line).marker.evaluate(default_environment() | PLATFORMS[platform])
        ]
        duplicates = {n for n in names if names.count(n) > 1}
        assert duplicates == set(), (platform, duplicates)


def test_pyproject_declares_no_dependencies():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert "dependencies" not in project and "optional-dependencies" not in project


def test_no_development_tool_in_the_runtime_file():
    for platform in PLATFORMS:
        assert set(pins(RUNTIME_FILE, platform)) & DEV_TOOLS == set()


def test_installed_versions_equal_the_pins():
    # CI installs requirements-dev.txt; anything else installed differently
    # (or missing) means the environment drifted from the declaration.
    mismatched = {}
    for name, req in pins(DEV_FILE).items():
        try:
            installed = distribution(req.name).version
        except PackageNotFoundError:
            installed = None
        if installed != pinned_version(req):
            mismatched[name] = (pinned_version(req), installed)
    assert mismatched == {}, f"installed differs from the pins (pinned, installed): {mismatched}"


def test_the_pinned_closure_is_complete_and_consistent():
    # Every requirement of every pinned distribution (markers and requested
    # extras evaluated for both platforms) is itself pinned, at a version that
    # satisfies it. Uses the installed metadata; a distribution installed only
    # on the other platform (colorama on Windows) has no requirements.
    problems = []
    for platform in PLATFORMS:
        env = default_environment() | PLATFORMS[platform]
        pinned = pins(DEV_FILE, platform)
        for name, req in pinned.items():
            try:
                dist = distribution(req.name)
            except PackageNotFoundError:
                continue
            for raw in dist.requires or []:
                sub = Requirement(raw)
                extras = req.extras or {""}
                if sub.marker is not None and not any(sub.marker.evaluate(env | {"extra": e}) for e in extras):
                    continue
                target = pinned.get(norm(sub.name))
                if target is None:
                    problems.append(f"{platform}: {req.name} needs {sub} but {sub.name} is not pinned")
                elif not sub.specifier.contains(pinned_version(target), prereleases=True):
                    problems.append(f"{platform}: {req.name} needs {sub}, pinned {pinned_version(target)}")
    assert problems == []


def imported_top_level_modules(paths: list[Path]) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                found.setdefault(name.split(".")[0], set()).add(str(path.relative_to(ROOT)))
    return found


def undeclared(paths: list[Path], allowed: dict[str, Requirement]) -> dict[str, list[str]]:
    providers = packages_distributions()
    missing = {}
    for module, files in imported_top_level_modules(paths).items():
        if module in sys.stdlib_module_names or module in LOCAL_PACKAGES or module == "__future__":
            continue
        dists = {norm(d) for d in providers.get(module, [])}
        if not dists & set(allowed):
            missing[module] = sorted(files)[:3]
    return missing


def python_files(*parts: str) -> list[Path]:
    files = []
    for part in parts:
        path = ROOT / part
        files += [path] if path.is_file() else sorted(path.rglob("*.py"))
    return [f for f in files if "__pycache__" not in f.parts and ".mypy_cache" not in f.parts]


def test_every_runtime_import_is_a_runtime_dependency():
    # What the production image runs: the app, the migrations and the
    # tenant-provisioning command.
    paths = python_files("app", "alembic", "scripts/provision_tenant.py")
    assert undeclared(paths, pins(RUNTIME_FILE)) == {}


def test_every_test_and_tool_import_is_declared():
    paths = python_files("tests", "pg_smoke", "boundary", "scripts")
    assert undeclared(paths, pins(DEV_FILE)) == {}
