# 历史压缩/单通道微基准（非验收工具）

此目录仅保留一套历史实验实现，不是生产 SDK、推荐 benchmark 或 Spec 符合性样例。当前工作入口是[扫描场景与算法审计](../../../docs/SCENARIO_AUDIT.md)。

## 保留内容

- [benchmark_single_channel_compressed.py](benchmark_single_channel_compressed.py)：合成 RF 的压缩/单通道读取实验，原样保留。
- [requirements.txt](requirements.txt)：原依赖版本下限，不是历史运行环境锁。
- 本地可能存在 `benchmark_results/` 和 `benchmark_results_10x/`，结果与缓存继续忽略，不保证随仓库分发。

旧六布局脚本、候选目录、MANIFEST 已从当前树移除；历史内容见 Git 提交 `8acf776`。完整精简边界见[归档说明](../../README.md)，证据局限见 [BENCHMARK_REPORT.md](../../../docs/BENCHMARK_REPORT.md)。

## 已知风险

- `--overwrite` 虽已解析但没有实施覆盖保护；执行可能覆盖目标目录中的同名产物。
- 未指定 `--keep-files` 时会删除对应的候选 HDF5 文件。即使指定该选项，也不防止覆盖。
- 合成源数据全量驻留 RAM，不能通过直接增大参数验证超过 RAM 的单文件。
- 缺少等价的严格输入拒绝、提交计数和逐请求读取校验；没有生产位置、参数、封存或恢复契约。
- 缓存、计时与可追溯性有已知局限，不用于布局/codec 排名或生产验收。

本轮未执行或修复此脚本，也不提供推荐复跑命令。如以后单独复查，必须先检查脚本行为并使用 `experiments/runs/` 下不存在的新专用目录，不能指向原始采集或既有结果。数据规范只在 [DATA_SPEC.md](../../../docs/DATA_SPEC.md) 维护。
