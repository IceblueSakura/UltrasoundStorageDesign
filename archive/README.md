# 归档说明

[返回项目入口](../README.md)。

本目录保存既有上游检出和历史微基准，与当前 [docs/](../docs/README.md) 设计及后续实现分开。归档是目录迁移，不删除文件，不将历史工具改造成新 SDK，也不表示这里的内容已获 Spec 符合性认证。

## 1. HDF5 源码

- 路径：`archive/hdf5/`，原位置为仓库根目录的 `hdf5/`。
- 完整保留嵌套 `.git`、工作树、未跟踪的 `flake.nix` 与 `flake.lock`。
- 父仓库继续忽略这个检出，不把它作为新 submodule 或 vendor 提交。
- 根 `flake.nix` 的可选 `hdf5-local` 已指向此路径；默认环境仍按锁定输入构建。
- 如需本地源码构建，参见[项目环境说明](../README.md)。不通过归档升级依赖或丢弃上游工作树改动。

上游仓库自带文档仍与源码一起保留，不作为当前项目的设计文档迁移到 `docs/`。

## 2. 历史微基准

路径：[benchmarks/ultrasound_storage_baseline/](benchmarks/ultrasound_storage_baseline/README.md)，原位置为根目录的 `ultrasound_storage_baseline/`。

保留脚本、requirements、候选目录、MANIFEST、现存 JSON/CSV 及 Python 缓存。原目录的五份 Markdown 文档已迁至 `docs/`；候选目录的文档引用已更新，其实验候选参数不变。

- [六布局脚本](benchmarks/ultrasound_storage_baseline/benchmark.py)
- [压缩/单通道脚本](benchmarks/ultrasound_storage_baseline/benchmark_single_channel_compressed.py)
- [常规结果](benchmarks/ultrasound_storage_baseline/benchmark_results/results.json)
- [10× 结果](benchmarks/ultrasound_storage_baseline/benchmark_results_10x/results.json)
- [证据报告](../docs/BENCHMARK_REPORT.md)

原始结果中的路径、时间、参数和统计值保持原样。历史 MANIFEST 保持原字节，包含已经缺失的旧结果和旧文档哈希；不能对迁移后的目录执行它并期待全部通过，也没有伪造新的历史哈希。

本地结果与缓存继续忽略，不自动随父仓库分发。后续归档新实验时应另建有明确来源的目录，不覆盖这些结果。

## 3. 后续工作的边界

新的 Spec 样例、只读检查器、SDK 或测试放到新的活动目录，而不是从归档中直接继承隐含规则。手动重跑旧脚本时输出到 `experiments/runs/` 下的新目录；运行说明与已知风险见[文档索引](../docs/README.md)。

本次不重跑实验、不修复测试行为、不删除缓存，也不 stage、commit 或修改嵌套 Git 历史。
