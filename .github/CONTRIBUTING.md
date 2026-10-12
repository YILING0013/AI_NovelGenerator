# 贡献说明 / Contributing

- 请基于最新 `main` 创建分支和 PR；`old` 仅保留旧版备份。
- 提交 Issue 前搜索已有问题，并在当前版本复现。一次报告一个问题，填写版本、操作系统、运行方式、复现步骤、预期与实际结果。
- 功能建议说明使用场景和预期行为；较大改动先通过 Issue 讨论范围。
- PR 一次解决一个明确问题，说明原因、实现和实际验证结果，关联对应 Issue。界面改动附中英文及窄屏截图；后端改动说明相关接口验证；涉及配置或数据变化时写清升级与回退办法。
- 本地最低检查：后端 Python 语法和导入正常，`python -m pip check` 通过；前端执行 `npm ci` 与 `npm run build`。没有执行的验证明确注明，不要把构建成功等同于全部业务通过。
- 不提交个人配置、密钥、小说数据、日志、构建产物、依赖目录或开发工具记录。截图和报错必须脱敏。
- 不将发布分支整体合并回旧版。旧版讨论统一关闭后，如新版仍有问题，请创建新 Issue 并链接旧讨论。

Base changes on current `main`; `old` is a legacy backup. Keep each issue or pull request focused, include reproducible steps and actual validation, and discuss large changes before implementation. Report configuration/data migration and rollback steps when applicable. Never submit secrets, personal data, novel content, generated output or unredacted logs. A closed legacy report does not imply that the current version has fixed it.
