from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from subprocess import CompletedProcess


DOCUMENT_SUFFIXES: set[str] = {".md", ".rst"}
FENCE_START = "```plantuml"
FENCE_END = "```"


class PlantUmlError(Exception):
    """Raised when PlantUML extraction or rendering fails."""


@dataclass(frozen=True)
class PlantUmlBlock:
    source_path: Path
    index: int
    start_line: int
    content: str


@dataclass(frozen=True)
class CheckResult:
    checked_blocks: int
    rendered_files: list[Path]


Runner = Callable[[list[str]], CompletedProcess[str]]


def extract_plantuml_blocks(path: Path) -> list[PlantUmlBlock]:
    """Extract fenced PlantUML blocks from a Markdown or reStructuredText file."""
    blocks: list[PlantUmlBlock] = []
    in_block = False
    start_line = 0
    lines: list[str] = []

    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not in_block and stripped == FENCE_START:
            in_block = True
            start_line = line_number
            lines = []
            continue

        if in_block and stripped == FENCE_END:
            blocks.append(
                PlantUmlBlock(
                    source_path=path,
                    index=len(blocks) + 1,
                    start_line=start_line,
                    content="\n".join(lines).strip() + "\n",
                )
            )
            in_block = False
            continue

        if in_block:
            lines.append(line)

    if in_block:
        raise PlantUmlError(f"{path}:{start_line}: missing closing ``` for plantuml block")

    return blocks


def check_documents(
    paths: Iterable[Path],
    output_dir: Path,
    *,
    plantuml_jar: Path,
    runner: Runner | None = None,
    java_command: str = "java",
) -> CheckResult:
    """Validate PlantUML blocks and render them through PlantUML."""
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered_files: list[Path] = []
    run_command = runner or _run_command

    for block in _iter_blocks(paths):
        _validate_block(block)
        output_path = output_dir / f"{_safe_stem(block.source_path)}_{block.index:02d}.puml"
        output_path.write_text(block.content, encoding="utf-8")
        rendered_files.append(output_path)

        command = [
            java_command,
            "-Djava.awt.headless=true",
            "-jar",
            str(plantuml_jar),
            "-tpng",
            str(output_path),
        ]
        result = run_command(command)
        if result.returncode != 0:
            message = result.stderr or result.stdout or f"PlantUML exited with {result.returncode}"
            raise PlantUmlError(f"{block.source_path}:{block.start_line}: {message.strip()}")

    return CheckResult(checked_blocks=len(rendered_files), rendered_files=rendered_files)


def iter_document_paths(paths: Iterable[Path]) -> list[Path]:
    """Return Markdown and RST files from files or directories."""
    documents: list[Path] = []
    for path in paths:
        if path.is_dir():
            documents.extend(
                candidate
                for candidate in sorted(path.rglob("*"))
                if candidate.is_file() and candidate.suffix.lower() in DOCUMENT_SUFFIXES
            )
        elif path.is_file() and path.suffix.lower() in DOCUMENT_SUFFIXES:
            documents.append(path)
    return documents


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract and render PlantUML fenced blocks from Markdown/RST docs.",
    )
    parser.add_argument("paths", nargs="*", type=Path, default=[Path("docs")])
    parser.add_argument("--jar", type=Path, default=_default_plantuml_jar())
    parser.add_argument("--output-dir", type=Path, default=Path(".plantuml-check"))
    parser.add_argument("--java", default="java")
    args = parser.parse_args(argv)

    if args.jar is None or not args.jar.exists():
        raise SystemExit(
            "PlantUML jar not found. Pass --jar /path/to/plantuml.jar "
            "or set PLANTUML_JAR."
        )

    documents = iter_document_paths(args.paths)
    result = check_documents(
        documents,
        args.output_dir,
        plantuml_jar=args.jar,
        java_command=args.java,
    )
    print(f"Checked {result.checked_blocks} PlantUML block(s).")
    return 0


def _iter_blocks(paths: Iterable[Path]) -> Iterable[PlantUmlBlock]:
    for path in paths:
        yield from extract_plantuml_blocks(path)


def _validate_block(block: PlantUmlBlock) -> None:
    lines = [line.strip() for line in block.content.splitlines() if line.strip()]
    if not lines or lines[0] != "@startuml":
        raise PlantUmlError(f"{block.source_path}:{block.start_line}: missing @startuml")
    if lines[-1] != "@enduml":
        raise PlantUmlError(f"{block.source_path}:{block.start_line}: missing @enduml")


def _run_command(command: list[str]) -> CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _safe_stem(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", path.stem).strip("_") or "diagram"


def _default_plantuml_jar() -> Path | None:
    value = None
    try:
        import os

        value = os.environ.get("PLANTUML_JAR")
    except Exception:
        value = None

    return Path(value) if value else None


if __name__ == "__main__":
    sys.exit(main())
