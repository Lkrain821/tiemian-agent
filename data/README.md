# 铁面数据目录

- `questions.json`：版本化种子题库，提交到项目。
- `tiemian.sqlite3`：运行时业务数据库，不提交。
- `checkpoints.sqlite3`：LangGraph checkpoint 数据库，不提交。

两个 SQLite 文件必须作为同一时间点的一组数据备份。业务代码不得查询或修改 checkpoint 内部表。

