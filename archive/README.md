# 归档说明

[返回项目入口](../README.md)。当前设计与场景审计位于 [docs/](../docs/README.md)，这里不是活动 SDK 或验收测试目录。

## 1. 本地 HDF5 源码

`archive/hdf5/` 保留既有上游检出、嵌套 `.git` 和本地文件，父仓库继续忽略；本轮不修改、删除或发布其中内容。它不是 submodule。默认开发环境不依赖该目录，可选本地源码构建方式见[项目说明](../README.md)。

## 2. 历史微基准的保留与精简

位置：[benchmarks/ultrasound_storage_baseline/](benchmarks/ultrasound_storage_baseline/README.md)。

- 保留 `benchmark_single_channel_compressed.py` 和 `requirements.txt`，仅作历史压缩/单通道实验参考。
- 移除旧六布局 `benchmark.py`、对应描述性 `candidate_catalog.json` 和已失效的 `MANIFEST.sha256`，不再维护重复候选入口或旧哈希清单。
- 旧脚本、候选和清单以及精简前的报告均可从 Git 提交 `8acf776` 查看，无需在当前树复制一套备份。
- 本地 `benchmark_results/`、`benchmark_results_10x/` 下的 JSON/CSV 与缓存不改写、不删除，继续忽略；原结果中的旧路径只是当时运行记录，不保证随克隆分发。
- 当前文档不再保留数值排名和复跑教程，限制说明集中于 [BENCHMARK_REPORT.md](../docs/BENCHMARK_REPORT.md)。

缩减历史材料不表示剩余脚本获得可靠性或符合性认证。旧脚本曾有的检查也不能转记为当前 Spec 用例已通过。

## 3. 使用边界

本轮不运行或修复旧基准，不构建上游源码。新样例、只读检查器和 SDK 应建立活动目录，不继承归档中的隐含规则。

如以后确需复查历史脚本，先阅读[风险说明](benchmarks/ultrasound_storage_baseline/README.md)，只用新的专用输出目录；不指向真实采集或既有结果。新实验结果建议放在已忽略的 `experiments/runs/`。
