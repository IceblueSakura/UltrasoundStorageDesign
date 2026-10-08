# 文档索引

[返回项目入口](../README.md)。本目录集中维护当前设计与 Spec，历史实验和上游源码存放在 `../archive/`，不与后续实现混放。

## 当前状态与阅读入口

**逻辑架构已收敛，已编写数据 Spec `0.1-draft`；精确编码、生产参数和 SDK 实现尚未完成。**

建议按“需求理由 → 数据契约 → 验证计划 → 性能证据”的顺序阅读：

- [DESIGN.md](DESIGN.md)：需求 R-01～R-11、范围与架构选择理由，不重复维护字段规则。
- [DATA_SPEC.md](DATA_SPEC.md)：数据契约的权威来源，区分〔确定〕、〔参考〕和〔待定〕；包括记录/位置关联、数值解释、参考 HDF5 映射及符合性边界。
- [SPEC_TEST_PLAN.md](SPEC_TEST_PLAN.md)：需求—规则—用例追踪、小样例和独立检查器计划；所有用例当前未执行。
- [BENCHMARK_REPORT.md](BENCHMARK_REPORT.md)：当前结果证据、测试局限与历史汇总的可追溯性说明，不是生产选型证明。
- [归档候选目录](../archive/benchmarks/ultrasound_storage_baseline/candidate_catalog.json)：旧布局实验的描述性目录和 Spec 引用，**不是可执行 JSON Schema，也不再复制规范字段表**。
- [旧六布局脚本](../archive/benchmarks/ultrasound_storage_baseline/benchmark.py)：随机 int16，包含 A/B/D/gate 和全通道 TCS 连续输出。
- [压缩/单通道脚本](../archive/benchmarks/ultrasound_storage_baseline/benchmark_single_channel_compressed.py)：合成 RF 的压缩/单通道读取基准。
- [常规结果 JSON](../archive/benchmarks/ultrasound_storage_baseline/benchmark_results/results.json) / [CSV](../archive/benchmarks/ultrasound_storage_baseline/benchmark_results/summary.csv)：56 个候选配置。
- [10× 结果 JSON](../archive/benchmarks/ultrasound_storage_baseline/benchmark_results_10x/results.json) / [CSV](../archive/benchmarks/ultrasound_storage_baseline/benchmark_results_10x/summary.csv)：32 个候选配置。

结果文件是本地实验产物，不保证随版本库分发。旧说明中的 `local_results/`、`small_write_batch_results/` 当前缺失，不能声称旧数值仍有完整原始记录可核对。[历史 MANIFEST](../archive/benchmarks/ultrasound_storage_baseline/MANIFEST.sha256)保留原字节，包含旧哈希和缺失路径，**不是当前工作树校验清单**；文档移动后的旧相对路径也不再适用。归档详情见 [archive/README.md](../archive/README.md)。

## 设计摘要

多通道共享触发、同构波形和每记录共享位置，由采集层组装完整记录后阻塞提交给 SDK。只做位置关联，不做时间同步。首版参考布局为 SPLIT，波形与位置既可单独读取，也可按同一记录选择绑定返回。

实时显示使用采集内存，普通文件读取在封存之后；异常文件尽力只读恢复。单文件需支持超过 100 GB、远超 RAM，不分卷。无损压缩用于降低磁盘流量和长期容量，允许第三方 filter；GPU 解压是待验证期望能力。

位置字段、采集与缓冲契约、查询权重、物理参数、恢复边界和 GPU 环境仍待细化。不把实验中的 `C=4`、u16、单通道工作负载或某个 chunk 值当成产品约束。范围见 DESIGN.md，待定项统一维护在 [Spec 登记表](DATA_SPEC.md#open-items)。

草案版本不自动承诺文件兼容，文档版本不是已分配的落盘 schema 值。当前可以验证部分规则或测试专用参考映射，必要编码未闭合前不宣称完整格式符合性。尚未实现样例生成器或独立检查器；推进条件见 [测试里程碑](SPEC_TEST_PLAN.md#milestones)。

## 两套实验不能混为一个 SDK

| 项目 | `benchmark.py` | `benchmark_single_channel_compressed.py` |
|---|---|---|
| 输入 | full-range 随机 int16 | 带噪声与脉冲的合成 RF；现存结果仅 u16 |
| 主要读取 | A/B/D/gate、连续 `[B,C,S]` 输出，包含布局转换 | 单通道批读、全读、gate、逐通道遍历 |
| 校验 | 严格 shape/dtype 负例、波形/状态/配置/前缀、逐请求检查 | 完整波形与状态回读；缺少严格输入、前缀及批读/gate 逐请求检查 |
| 覆盖保护 | 检查目标输出冲突，需显式 `--overwrite` | 已解析 `--overwrite` 但未执行覆盖保护，必须使用新目录 |
| GPU | 可选串行 pinned-host H2D 分支；未验证 GPU 解压 | 没有 GPU 解压路径 |

两者都不是生产 SDK，实验文件不满足完整自解释格式，未实现共享位置契约、真实参数快照、封存拒写、只读恢复或真实设备持续输入。旧基准的配置索引仅为零占位，新压缩基准没有该索引。当前代码能力以脚本为准，不能将设计要求视为已实现。

## 手动运行示例

以下命令从**仓库根目录**执行，不在 `docs/` 或归档目录中执行；本次迁移没有执行这些命令。需要 Python 3.11+ 和合适的环境。输出使用 `experiments/runs/` 下不存在的新目录，不能覆盖归档结果：

```bash
python -m pip install -r archive/benchmarks/ultrasound_storage_baseline/requirements.txt
python archive/benchmarks/ultrasound_storage_baseline/benchmark.py --out experiments/runs/results_baseline_new
python archive/benchmarks/ultrasound_storage_baseline/benchmark.py --out experiments/runs/results_small_batch_new --write-batch 16
python archive/benchmarks/ultrasound_storage_baseline/benchmark_single_channel_compressed.py --out experiments/runs/results_compressed_new
```

也可在仓库根目录使用 `nix develop` 提供的环境。`requirements.txt` 是版本下限而非完整环境锁；不得据此推定历史实验的精确运行库。

**两套脚本都将完整合成源数据保留在 RAM 中。不要用增大参数到 100 GB 的方式验证超 RAM 需求。** 流式生成、有界缓冲和受控缓存实验仍待实现。

始终使用新的、专用于可丢弃实验产物的输出目录，尤其不要将压缩基准指向现有结果或真实采集目录。`--keep-files` 保留生成的 HDF5 文件，否则脚本会删除对应的候选 HDF5 文件。此工具包不迁移生产文件。

旧基准可选 CUDA 分支：

```bash
python archive/benchmarks/ultrasound_storage_baseline/benchmark.py --out experiments/runs/results_cuda_new --gpu
```

它要求预先配置可用 CUDA PyTorch，不安装驱动或工具链。无 CUDA 时记录 `NOT_RUN`。该路径是主机读取/重排后串行 H2D 并同步，不是 GPU 解压、GPUDirect、流水线重叠或计算性能证明。

## 计时边界

写入包括重排、resize、每批两次 HDF5 flush 和 close，不含源生成、文件初始化或 fsync；不是持久化磁盘带宽。读取前进行了完整校验/预热，未清空 OS 缓存。压缩基准不独立重复整套读取，也不保存读取原始计时序列。

波形 raw chunk cache 预算按 SPLIT 通道拆分；总预算相同不代表活跃单通道可用缓存相同，其他 dataset/元数据/OS 缓存也未完全均衡。不能把热缓存逻辑读取吞吐称为纯解压速度或磁盘速度。

A/B/D/gate 是数据选择而非成像，B/D 采用项目局部命名约定。更多证据缺口和后续测试边界见 BENCHMARK_REPORT.md 与 DESIGN.md。
