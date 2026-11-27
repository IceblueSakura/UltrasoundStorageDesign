# 剩余开放项与 M2 待补输入清单

状态：已依据 [ADR-0001～ADR-0020](decisions/README.md) 完成 Core 首版架构与工程选型定型；原 16 个工程决策角度中的全部架构分叉均已闭合，本文遵循 [ADR-0007](decisions/0007-documentation-structure.md) 仅维护**尚未闭合的事实输入、M2 细化项与后置项**。唯一 `D-01`–`D-19` 权威状态总表见 [DATA_SPEC.md](DATA_SPEC.md#open-items)，已定工程合同见 [SDK_CONTRACT.md](SDK_CONTRACT.md)。

---

## 1. 已定型决策速查（不再重复展开）

| 主题域 | 闭合结论摘要 | 权威 ADR / 合同 |
|---|---|---|
| 模型基线（`Q1–Q7`、`D-15`） | 两层架构、中立容器 UUID、分模式独立 Schema、解除 `h5py` 裸读、Write-Once 封存、关闭 `D-15` | [ADR-0016](decisions/0016-tiered-core-mode-schemas-and-immutable-seal.md) |
| 首版范围与业务模型（`D-03/04/09/11/16`） | 首版单晶 + PA + 伴生/旁路快照（预留 `FeatureOnly`/`FMC`）；轻量 M:N `Region`；统一快照 + Write-Once 旁路容器；最小解码核 + DICONDE/NeXus 可选物理表 + 参数化曲面几何；可配置 `(F_chunk, K_chunk, S)` 默认 1–4 MiB | [ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md) |
| P0 物理引擎与故障语义（`D-05/10`） | 正式采用 `MAP-02` + 按 Scan SWMR；拒绝正常 0 帧 Scan / 0-Scan 封存；写失败禁原位重试；双槽提交全毁不可恢复；坚持 `push` 两阶段读 | [ADR-0018](decisions/0018-storage-engine-swmr-and-strict-lifecycle.md) |
| <a id="angle-15"></a>P1 编码与 Core I/O（`D-01/02/04/07/08/10`，含原角度 15） | 固定列式位置/`pos_valid`/同步等级/`CellCoord`/`required\|nullable` 附加记录；LSB-first packed bitset + Writer/Scan 严格模式 + 越界/空选择整体拒绝；`{i8..u32, f32}` + `XXH3-64`；`none`/`shuffle+zstd`/`shuffle+lz4`（去 `deflate`）；连续 + 离散按块合并 Batch、每组独立缓冲与块几何/容量查询（适配 UMS `Batch-of-SoA`） | [ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md)、[SDK_CONTRACT.md](SDK_CONTRACT.md) |
| <a id="angle-16"></a>技术栈、绑定与版本门禁（`D-07/12`，含原角度 16） | C++20 核心 + 纯 C11 ABI；静态打包 HDF5 2.x + zstd + lz4 单库分发；首版（M3）仅交付 C ABI + `.NET`（`net10.0`/`net48`），Python 官方绑定延后至 M4；Format/Schema/SemVer 三轴解耦，`1.0` 冻结并启用 SONAME/符号版本/`abidiff` | [ADR-0020](decisions/0020-implementation-stack-bindings-and-versioning.md)、[SDK_CONTRACT.md](SDK_CONTRACT.md) |

---

<a id="business-next"></a>
## 2. 进入 M2 工程定型前仅剩的 2 类未闭项

### 2.1 待补充的真实设备与负载事实输入（非架构分叉）

以下三项不涉及结构取舍，只需上游（UMS / 真实设备）提供具体事实样本与数字：

| 关联 D 项 | 所需事实输入 | 归位与作用 |
|---|---|---|
| **D-09**（设备物理字段清点） | 首批单晶与相控阵设备的真实采集方案与单帧交付示例：事件—接收输出—通道/声束映射、最小必填核与 DICONDE/NeXus 标准可选物理参数具体字段清单及单位、曲面采用几何实际参数 | 校验 `SingleProbe` / `PhasedArray` 首版 Schema 字段完备性（记录入 [SCENARIO_AUDIT.md](SCENARIO_AUDIT.md)） |
| **D-02**（规模与全链路内存预算） | 首发模式典型/最大 `K_g`、`S_g`、最大单 Frame 字节数、持续/突发写入速率，以及全链路（调用者 `Batch-of-SoA` + SDK 组装/暂存缓冲 + HDF5 + `.NET` 绑定）峰值内存门槛 | 设定 M2 上限常量与 M3 超 RAM（`T-18`/`T-19`）验收门槛 |
| **D-03 / D-04**（负载权重与实测校准） | 五类访问场景（C 扫快照浏览、点选 A 波、区域批读、B/D/S 切片、全扫遍历）的实际频率权重、目标主机/磁盘基准，以及延迟/吞吐目标 | M3 实测校准默认块目标大小（1–4 MiB 内微调）与 `zstd` 默认级别 |

### 2.2 M2 冻结前的工程细化与取证任务（方向已定，待出细则/实测）

| 优先级 | 关联 D 项 | M2 具体交付物与闭合条件 |
|---|---|---|
| **P0（冻结门禁）** | **D-05** | 补跑一次单 Scan 数千块（多级 HDF5 chunk B-tree 索引）的 `MAP-02 + SWMR` 随机 SIGKILL 与非 SWMR 建对象短窗公开只读 VFD 恢复实验，固化多级索引崩溃证据 |
| **P1（wire 规范）** | **D-07 / D-01 / D-11 / D-16** | 起草无 `TBD` 的 HDF5 Wire Format 1.0 规范：容器/旁路角色标识、`FileInstanceUUID`、轻量 M:N `Region` 字段名、分模式 Schema 路径、列式位置/`CellCoord`/附加记录存储、LSB-first 位图、双槽提交与 `XXH3-64` 校验表、伴生/旁路快照编码、`EndStatus` 编码，并通过 HDF5 1.14 独立读取器验通（`T-22`/`UC-27`） |
| **P1（C11 头文件）** | **D-10 / D-08** | 起草纯 C11 头文件 `uss.h`：完整函数签名、选项结构体、`COMMITTED/NOT_COMMITTED/UNKNOWN` 提交状态、稳定错误码与分类枚举、完整 File/Scan/Writer/Reader 状态转换表、离散/连续 Batch 与容量查询接口 |
| **P1（平台下限）** | **D-12** | 明确 Linux LTS 发行版/glibc 下限、GCC/Clang 与 Windows MSVC 版本矩阵，以及 M3 Windows + `.NET Framework 4.8` 实测清单 |

---

## 3. 独立扩展层与明确后置项（归 M4 或后续，不阻塞 Core M2/M3）

| 分层 | 议题与 D 项 | 现状与启动前提 |
|---|---|---|
| **独立扩展层（M4）** | **3D 旁路空间索引与多回波代表选择（`D-17`）** | 仅消费 Core 只读 API（Core 原生已交付 `0~N` 来源与可选 `CellCoord`）；待核心稳定后定义旁路索引格式与可插拔策略接口 |
| **独立扩展层（M4）** | **窗口选峰基础取值（`D-18`）** | 仅消费 Core 只读 API；前沿成对输出同一点位置/时间与幅值已定，等待用户统一提供算法参考判据与未检出语义 |
| **绑定与加速（M4）** | **官方 Python 绑定（`D-12` 后置项）** | 首版优先 C ABI + `.NET`；M4 按需交付建于 C ABI 之上的 Python 绑定与受检 NumPy 视图 |
| **绑定与加速（M4）** | **可选 GPU 直接解压（`D-06`）** | 编码链已选定 `shuffle+zstd`/`shuffle+lz4` 衔接 `nvCOMP`；M4 实测完整逆变换、尾块一致性与端到端 H2D 收益 |
| **扩展模式（后置）** | **`FeatureOnly`（仅特征）与 `FMC` 模式细节** | 容器 Schema 枚举已预留；待单晶/PA 首版闭环后展开对应字段与测试夹具（`FMC-01/02` 逻辑语义已定） |
| **明确后置** | **混合扫描与多探头（`D-13`）、部分/跨组矩阵（`D-14`）** | 待真实多模式/多独立运动探头或 HMC/PWI/Sparse 设备需求明确后再补正反样例与规则修订 |
| **明确后置** | **多文件组织与跨文件复检（`D-19`）** | 待用户规划 dataset/group/多文件集合解析模型；定案前跨文件复检由 UMS 逻辑成果持有 |

---

## 4. 补充事实与后续裁决归位方式

后续补充设备事实或进入 M2 细化时，严格按 [ADR-0007](decisions/0007-documentation-structure.md) 归位：架构/需求变动入 `DESIGN.md`；数据与存储契约入 `DATA_SPEC.md`；C ABI、Profile 与绑定工程合同入 `SDK_CONTRACT.md`；新拍板决定一页一事入 `docs/decisions/`；设备与负载证据入 `SCENARIO_AUDIT.md`；验证用例与门槛入 `SPEC_TEST_PLAN.md`。
