# ADR-0017：Core 首版范围、数据模型细化与可配置物理分块

- 状态：已采纳（2026-11-27）；定型 Core 首版业务模型与分块策略，wire 编码与字段名在 M2 细化。
- 规则落点：[DOC-01](../DATA_SPEC.md#doc-01)、[REL-01](../DATA_SPEC.md#rel-01)、[SCAN-02](../DATA_SPEC.md#scan-02)、[SNAP-01](../DATA_SPEC.md#snap-01)、[META-01](../DATA_SPEC.md#meta-01)、[MAP-01](../DATA_SPEC.md#map-01)、[SDK_CONTRACT.md](../SDK_CONTRACT.md)；收口 `D-03`、`D-04`、`D-09`、`D-11`、`D-16` 架构方向。
- 来源：用户在 `ADR-0016` 之后开展的一组定型决策（2026-11-27）。

## 背景

[ADR-0016](0016-tiered-core-mode-schemas-and-immutable-seal.md) 收敛了两层架构、分扫描类型独立 Schema 与原始文件 Write-Once 不可变封存，但 Core 首版推进范围以及 `D-11`（文件内 `Region` 形态）、`D-16`（伴生快照与旁路派生容器形态）、`D-09`（单晶/相控阵物理参数与曲面几何边界）、`D-03`/`D-04`（A/B/C/D/S 五类访问对应的物理分块模型）仍存在架构分叉，制约进入 M2 格式与 ABI 设计。

## 决定

1. **Core 首版推进范围明确收口。** 首版（M2 冻结与 M3 交付）聚焦 **单晶（SingleProbe）+ 相控阵（PhasedArray）+ 伴生/旁路 C 扫快照**，同步定型物理引擎、C11 ABI 与技术栈；仅特征采集（`FeatureOnly`）与全矩阵捕获（`FMC`）在容器 Schema 类型枚举中保留预留口，本轮不展开字段细节；独立可选扩展层（`D-17`/`D-18`）、GPU 解压（`D-06`）、混合扫描（`D-13`）、部分/跨组矩阵（`D-14`）与跨文件组织（`D-19`）明确后置。
2. **文件内 `Region` 采用“轻量元数据实体 + M:N 引用”（收口 `D-11` 方向）。**
   - `Region` 仅保存身份与轻量描述：`region_id`、可读 `name`、可选包围盒/坐标参考系标识与带类型 `VendorExtension`，不内置复杂多边形/CAD 几何引擎或空间归属校验。
   - `Scan` 与 `Region` 允许 **M:N 引用**：单 `Scan` 可选关联 `0..N` 个目标 `Region`，多个 `Scan` 可共享同一 `Region`；未采集的已声明 `Region` 合法留空以表达计划缺口。文件内复检由新 `Scan` 可选指向原 `ScanID`/`RegionID`。
3. **统一快照模型 + Write-Once 旁路容器（收口 `D-16` 方向）。**
   - 封存前采集期伴生 C 扫快照与封存后离线派生快照共用同一逻辑模型：支持规则 2D 栅格或稀疏点表，记录特征数值层、逐点状态、实际来源引用 `(ScanID, FrameIdx, Stream/BeamID)` 与实际采用参数。
   - 离线旁路派生文件同样是本 SDK 管理的 **Write-Once HDF5 容器**（`file_role = DerivedSnapshot`），头部强绑定原始文件的 `FileInstanceUUID` 与 `ScanID`；替换/更新快照通过写新临时文件并原子 `rename` 完成，确保写入失败时既有可用成果完好无损。
4. **分模式参数采用“最小解码必填核 + 强类型标准可选物理表 + `VendorExtension`”（收口 `D-09` 方向）。**
   - **最小必填核**：仅强制缺少即无法解码或建立映射的字段——`SignalDescriptor`（原始位宽/dtype、有效 ADC 位、对齐/端序、偏置/比例、采样轴与起点延迟、信号处理层次标签）、通道/探头标识，以及 PA 的阵元与聚焦法则/声束映射。
   - **强类型标准可选字段**：参照 ASTM DICONDE（E2339/E2738）与 NeXus 核对清单定义探头频率、带宽、增益、声速、楔块、滤波、坐标系等标准可选字段，避免强迫外部简单扫描系统伪造缺省参数。
   - **曲面采用几何**：仅存解释已有数据必需的轻量参数化描述（平面/柱面/球面等基本曲面参数或外部参考曲面标识＋坐标系/姿态/法向），不内嵌点云或三角网格；厂商专有配置统一放进带 `(vendor_id, schema_uri, version)` 的 `VendorExtension`。
5. **物理分块格式支持可配置 `(F_chunk, K_chunk, S)`，首版默认帧主序自适应 1–4 MiB（收口 `D-03`/`D-04` 布局方向）。**
   - 格式层允许在 Scan 固定定义中声明三维分块几何 `(F_chunk, K_chunk, S)`（单条波形 `S` 维不切分，避免单 A 波跨块），`MAP-02` 按每满 `F_chunk` 帧一次性写出对应 `ceil(K / K_chunk)` 个块并记入校验表。
   - 首版默认策略为 `K_chunk = K`、按目标未压缩块大小 **1–4 MiB** 自适应 `F_chunk`（写入方可按 D 扫交互或顺序吞吐偏好显式覆写），在 A/S 扫毫秒级解码、B 扫与离线 C 扫全扫吞吐以及 100 GB 文件 2–5 万级浅 B-tree 块索引间取得平衡；M3 结合真实负载微调默认值无需改格式。

## 理由

- 聚焦单晶 + 相控阵可让 M2/M3 尽快形成端到端可用闭环，同时通过 Schema 类型枚举为仅特征与 FMC 留足演进空间。
- M:N 轻量 `Region` 既适配 UMS“每区域一段”的顺序执行，也不阻断外部系统“一次扫描覆盖多区域”的合法建模。
- 伴生与旁路快照统一模型且均采用 Write-Once，彻底消除了旁路文件自身原地改写导致的崩溃损坏与锁复杂度。
- “最小解码核 + 标准可选表”平衡了 UMS 完备自描述需求与外部系统低门槛接入；可配置 `(F_chunk, K_chunk, S)` 避免格式层把 PA 单束 B 扫或 D 扫调优路堵死。

## 后果与未决项

- `D-11` 仅剩精确字段名与序列化编码；`D-16` 仅剩快照数据层与旁路容器的 wire 编码；`D-09` 仅剩首批单晶/PA 设备的具体字段清点；`D-03`/`D-04` 仅剩真实负载权重与默认值实测校准。
- 修订 [ADR-0011](0011-ultrasound-business-boundary.md)、[ADR-0013](0013-region-relations-and-subset-scope.md)、[ADR-0014](0014-configurable-selection-and-snapshot-source.md)、[ADR-0016](0016-tiered-core-mode-schemas-and-immutable-seal.md) 中仍标注待定的对应模型方向，不改变既有已采纳边界。
