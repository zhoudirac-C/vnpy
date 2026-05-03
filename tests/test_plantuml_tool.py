from pathlib import Path
from subprocess import CompletedProcess

import pytest

from tools.plantuml.check_plantuml import (
    PlantUmlError,
    check_documents,
    extract_plantuml_blocks,
)


def test_extract_plantuml_blocks_records_source_and_line(tmp_path: Path) -> None:
    doc_path = tmp_path / "architecture.md"
    doc_path.write_text(
        "\n".join(
            [
                "# Architecture",
                "",
                "```plantuml",
                "@startuml",
                "Alice -> Bob: hello",
                "@enduml",
                "```",
            ]
        ),
        encoding="utf-8",
    )

    blocks = extract_plantuml_blocks(doc_path)

    assert len(blocks) == 1
    assert blocks[0].source_path == doc_path
    assert blocks[0].index == 1
    assert blocks[0].start_line == 3
    assert "Alice -> Bob" in blocks[0].content


def test_check_documents_rejects_incomplete_plantuml_block(tmp_path: Path) -> None:
    doc_path = tmp_path / "broken.md"
    doc_path.write_text(
        "\n".join(
            [
                "```plantuml",
                "@startuml",
                "Alice -> Bob: missing end",
                "```",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(PlantUmlError, match="missing @enduml"):
        check_documents([doc_path], tmp_path / "out", plantuml_jar=tmp_path / "plantuml.jar")


def test_check_documents_writes_blocks_and_invokes_renderer(
    tmp_path: Path,
) -> None:
    doc_path = tmp_path / "ok.md"
    jar_path = tmp_path / "plantuml.jar"
    calls: list[list[str]] = []
    doc_path.write_text(
        "\n".join(
            [
                "```plantuml",
                "@startuml",
                "participant Alice",
                "participant Bob",
                "Alice -> Bob: hello",
                "@enduml",
                "```",
            ]
        ),
        encoding="utf-8",
    )
    jar_path.write_text("fake jar", encoding="utf-8")

    def fake_run(command: list[str]) -> CompletedProcess[str]:
        calls.append(command)
        return CompletedProcess(command, 0, stdout="", stderr="")

    result = check_documents(
        [doc_path],
        tmp_path / "out",
        plantuml_jar=jar_path,
        runner=fake_run,
    )

    assert result.checked_blocks == 1
    assert result.rendered_files == [tmp_path / "out" / "ok_01.puml"]
    assert result.rendered_files[0].read_text(encoding="utf-8").startswith("@startuml")
    assert calls == [
        [
            "java",
            "-Djava.awt.headless=true",
            "-jar",
            str(jar_path),
            "-tpng",
            str(tmp_path / "out" / "ok_01.puml"),
        ]
    ]
