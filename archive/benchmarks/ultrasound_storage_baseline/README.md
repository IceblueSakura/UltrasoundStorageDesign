# 历史超声存储微基准

本目录保存原 `ultrasound_storage_baseline/` 的脚本和本地实验产物，不是活动 SDK 或 Spec 符合性样例。

- [归档说明](../../README.md)：迁移范围、历史清单及结果保留策略。
- [当前文档入口](../../../docs/README.md)：设计状态与手动运行说明。
- [性能证据报告](../../../docs/BENCHMARK_REPORT.md)：现存结果核对及局限。
- [数据 Spec](../../../docs/DATA_SPEC.md)：当前数据契约；候选目录仅引用它。

脚本、requirements、MANIFEST、结果及缓存原样保留；`candidate_catalog.json` 只更新规范引用路径。历史 MANIFEST 不适用于当前目录校验。原始 JSON 中的旧输出路径保持为历史事实。

压缩脚本未执行 `--overwrite` 覆盖保护。只在确认的新专用目录手动运行，输出放到仓库根目录下的 `experiments/runs/`，不要写回归档。本次迁移没有运行任何基准。
