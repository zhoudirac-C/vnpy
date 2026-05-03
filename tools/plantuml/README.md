# PlantUML 文档检查工具

本目录提供仓库内的 PlantUML 文档检查脚本，用于从 Markdown/RST 文件中抽取 fenced PlantUML 图块并调用 PlantUML 渲染。

用法：

```bash
PLANTUML_JAR=/path/to/plantuml.jar \
uv run python -m tools.plantuml.check_plantuml docs
```

也可以显式传入 jar：

```bash
python -m tools.plantuml.check_plantuml \
  --jar /path/to/plantuml.jar \
  --output-dir /tmp/vnpy-plantuml-check \
  docs/community/info/custom_quant_architecture.md
```

约定：

- 文档图块统一使用 fenced code block：```` ```plantuml ````。
- 每个图块必须以 `@startuml` 开始、以 `@enduml` 结束。
- 工具会把抽取出的 `.puml` 文件写到 `--output-dir`，并用 PlantUML 生成 PNG，以便捕获语法错误。
