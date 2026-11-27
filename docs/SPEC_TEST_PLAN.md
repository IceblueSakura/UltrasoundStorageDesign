# 访问场景映射与 Spec 验证计划

状态：已依据 [ADR-0001～ADR-0020](decisions/README.md) 完成 Core 首版定型，并合并原访问用例规划；本轮不修改或重跑既往代码/实验，产品 `UC` 与 `T` 均未执行，M1 test-only 证据仅保留其原适用范围。

总体边界见 [DESIGN.md](DESIGN.md)，唯一数据与存储契约见 [DATA_SPEC.md](DATA_SPEC.md)，首版工程合同与接口规格见 [SDK_CONTRACT.md](SDK_CONTRACT.md)，场景与历史基准局限见 [SCENARIO_AUDIT.md](SCENARIO_AUDIT.md)。本文不新增契约规则或性能数值门槛。

## 1. 分离验证目标与消费场景分工

### 1.1 四类分离验证目标

| 类型 | 目标 | 当前边界 |
|---|---|---|
| 符合性 | 验证语义、结构、关联和拒绝行为 | 先用小型、逐项可核对的独立期望样例推进 |
| 规模/性能 | 验证有界内存、持续写入及访问代价 | 数值目标仍待 `D-02`/`D-03` 事实输入；不能替代符合性 |
| 故障恢复 | 验证 `MAP-02` + 按 Scan SWMR 进程崩溃与原地只读恢复 | 必需的尽力恢复目标；不承诺断电/OS 崩溃（`ADR-0008`） |
| 可选加速 | 验证 M4 GPU `nvCOMP` 完整编码链解码一致与端到端收益 | 非 Core M3 必选 |

每个用例记录 Spec 修订/哈希、规则 ID、实现版本、样例版本、临时编码选择、环境与原始结果。严格区分 `PASS`、`FAIL`、`NOT_RUN`、`BLOCKED`、`UNSUPPORTED`；已被替代的历史用例不计为 `PASS`。

<a id="access-mapping"></a>
### 1.2 访问场景分层与 `UC` 追踪（合并自原访问规划）

读取覆盖文件中保存的全部超声内容（[BUS-01](DATA_SPEC.md#bus-01)、[ADR-0015](decisions/0015-cross-system-data-delivery.md)），五类重点场景（浏览 C 扫快照、点选 A 波、区域批读/取值、B/D/S 布局切片、全扫遍历）通过可配置 `(F_chunk, K_chunk, S)` 分块与连续/离散按块合并 Batch 兼顾（[ADR-0017](decisions/0017-core-v1-scope-and-domain-model.md)、[ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md)）：

| 消费场景域 | 核心请求与交付重点（规则见 `DATA_SPEC` / `SDK_CONTRACT`） | 追踪入口 |
|---|---|---|
| 中立容器、多 Scan 独立与严格生命周期 | 枚举 UUID / 轻量 M:N `Region` / `Scan`；拒绝正常空 Scan/空文件；拒向已完成或已封存文件追加；`LIF-02` 原地只读逐 Scan 恢复 | UC-17、UC-19；T-12/T-15 |
| 文件内 `Region` 与复检关系 | 文件内轻量 M:N `Region`（`D-11` M2 字段定稿）；跨文件复检留待 `D-19` | UC-18（跨文件项 BLOCKED） |
| 单晶异构与帧内选择 | 跨组保留各自 `τ_g`/`S_g`/采样轴；流与样本清单保序保重复；越界与空选择整体拒绝 | UC-01～05 |
| PA 完整帧、声束集与无定位读取 | 一帧共用唯一 `P_n`，显式 `pos_valid` 与同步等级，束 `[2,0,2]` 保序保重复 | UC-06～08、UC-21 |
| FMC 矩阵、子矩阵、配对与 Q 表（预留模式） | 显式 π（拒缺口/别名/悬空/冲突），配对不展开、互易对独立、异构不强转、Q 逐对选样 | UC-09～13（FMC 首版预留） |
| 双模式 Batch、`poll`/`push` 与超 RAM | 连续 `(start, count)` 与离散帧清单按块合并解码；每组独立稠密缓冲；`poll` 借用与 `push` 两阶段原子性；块几何/容量查询对齐 `Batch-of-SoA` | UC-14；T-06/T-14/T-18 |
| 有效全 0 / 无效零填充 / 重复位置 | LSB-first packed bitset 区分有效全 0 与 `valid=0` 零填充；不合并重复位置帧 | UC-15、UC-16 |
| 三种保留、伴生与 Write-Once 旁路快照 | 按保留模式交付；伴生快照来源不变；封存后原始文件不可改写；离线派生写 Write-Once 旁路容器并原子 `rename` 保旧 | UC-20、UC-24 |
| 分模式 Schema、原生寻址、规范子集与外部互通 | 单晶/PA 最小解码核 + 可选物理表 + 参数化几何 + `VendorExtension`；按触发/束/通道/`CellCoord` 返回 `0~N` 来源与四类子集；外部创建与 1.14 独立读取 | UC-22、UC-26、UC-27；T-21/T-22 |
| **M4 独立可选扩展层（不阻塞 Core）** | 3D 旁路空间索引与可插拔多回波选择（`D-17`）；窗口选峰峰峰值与前沿成对输出（`D-18`） | UC-23、UC-25（BLOCKED，归 M4） |

- **TFM 与离线算法消费边界**：离线重建/TFM 消费单 Frame 或 Batch 块后在内存中按逐对选样表取样（避免逐像素磁盘 I/O）；稠密形状不代表共同物理时间轴；算法须连同有效性位图消费样本（不把 `valid=0` 填充值当真实零回波）；`Tx/Rx` 不是空间网格，派生结果绝不改写原始文件。

## 2. 小型样例策略

首轮使用容易逐项核对的小数据，不追求吞吐：

- 各 Frame 和流的样本值可区分，避免全零掩盖错配；基础正例显式提交 `valid=1`，变体单独列出 `valid=0` 槽位。
- test-only 位置既区分帧又包含重复位置值（防以坐标代替 Frame 身份）；固定定义跨帧复用，定义变化用拒绝反例。
- 有效非零、有效全 0 与无效零填充须共同覆盖；`valid` 位只管原始波形槽位，不替代 [RET-01](DATA_SPEC.md#ret-01) 的保留与缺口状态。
- 未定 wire 编码采用明确标注的 `test-only` 编码并记录，不反推为生产默认值；损坏样例生成在专用隔离目录。

流组划分（[ADR-0001](decisions/0001-stream-groups.md)）：`H` 三条异构流各自独占 `K_g=1` 流组；`P` 三个声束为 `K_g=3` PA 声束集；`F` 九个收发对为 `K_g=9` Tx×Rx 矩阵组（FMC 首版预留，语义回归保留）；`W` 每个 Scan 各一组。

<a id="semantic-fixtures"></a>
### 2.1 异构单晶样例 H

三条流、两个 Frame，固定长度和 dtype。以下数值是独立期望，不是设备默认值；样例尚未生成。

| 流 | dtype / 长度 | Frame 0 | Frame 1 |
|---|---|---|---|
| W0 | u8 / 4 | `[0,127,128,255]` | `[1,126,129,254]` |
| W1 | u16 / 3 | `[0,256,65535]` | `[1,257,65534]` |
| W2 | i32 / 5 | `[-2147483648,-1,0,65536,2147483647]` | `[-2147483647,-2,1,65537,2147483646]` |

Frame 0/1 使用抽象位置 P0/P1。目标为异构、符号、位宽、数据身份和无隐式转换（另配 `f32` 变体覆盖 `-0.0` 与自定义 `NaN` payload 按位无损保真，[ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md)）。

共同样本请求 `[3,4)` 对 W0/W2 合法、对 W1 越界：按 [ADR-0019](decisions/0019-wire-encoding-and-core-io-contracts.md) 整个请求**整体拒绝**并返回明确越界错误码，不得静默截断、补零或返回部分流成功。

有序样本清单变体：Frame 0、W0、Sample `[3,1,3]` 的独立预期为 `[255,127,255]`，样本身份依次为 `s=3、1、3`，Frame/流来源和槽位状态不变。相同清单对 W1 越界同样整体拒绝；追踪 `READ-02 / U-09 / UC-12`。

### 2.2 常规 PA 样例 P

两个 Frame、三个声束、每波形八点、测试 dtype u16：

```text
W[n,b,s] = 1000*n + 100*b + s
```

每帧仅有一个 `P_n`（配显式 `pos_valid` 与同步等级）。固定几何 G、法则 L0/L1/L2 各定义一次；束 b 能追溯到正确事件、接收输出及 `L_b`。

Frame 1、束顺序 `[2,0,2]`、样本 `[1,4)`：

```text
b2 → [1201,1202,1203]，Frame 1、P1、G、L2
b0 → [1001,1002,1003]，Frame 1、P1、G、L0
b2 → [1201,1202,1203]，Frame 1、P1、G、L2
```

检查引用而不计算束坐标；增加 `P0=P1` 变体，两个 Frame 不合并。不执行定位也可原始读取，派生位置不能替换 `P_n`。

UC-06/07 的位置变体可用 A/B 编码器描述，固定在 Scan 内，每帧一对值，全部声束共享；另以列式 `nullable` 帧级附加记录保存理论坐标标记，按同一 Frame 关联、不替换原始位置。跨 Scan 使用不同位置描述的变体追踪 UC-17。

### 2.3 FMC 样例 F（首版模式预留，保留语义基线）

两个 Frame、三个 Tx、三个 Rx、八样本，测试 dtype u16：

```text
X[n,i,j,s] = 1000*n + 100*i + 10*j + s
```

I/J 为同一选定三阵元集合，π 声明全部九个有序收发对与流的对应。流的物理/目录顺序可与 π 的矩阵顺序不同，以验证读取不从排列猜 Tx/Rx。

#### FMC 映射拒绝反例（UC-09 变体）

各反例从合法 F 定义单独改变一项，保留其他映射、样本及解释；验证 [FMC-01](DATA_SPEC.md#fmc-01) / U-06 与 [FMC-02](DATA_SPEC.md#fmc-02) / U-07：

| 单项变更 | 独立拒绝预期 |
|---|---|
| 保持完整 I×J 声明，删除 `(2,1)` 的 π 映射 | 报告声明域覆盖不完整；不得缩小矩阵、补零或借互易对补齐 |
| 将 `(0,2)` 和 `(2,0)` 映射到同一逻辑流 | 报告不同有序对的测量身份别名冲突；不得以互易性接受 |
| 将 `(1,2)` 映射到不存在的流 | 报告悬空流引用；不得从目录位置选择替代流 |
| 保持 π 指向的流存在，但使 `(2,1)` 对应流的事件 Tx 身份变为集合外的 Tx9 | 报告映射与事件发射身份不一致；不能仅凭 shape/dtype 接受 |
| 保持 π 指向的流存在，但使 `(2,1)` 对应流的接收输出身份变为集合外的 Rx9 | 报告映射与接收输出身份不一致；不能仅凭硬件通道或目录顺序接受 |

#### 正确选择的独立期望

Frame 0、Tx `[2,0]`、Rx `[1,2]`、样本 `[2,5)`：

```text
             Rx1               Rx2
Tx2     [212,213,214]     [222,223,224]
Tx0     [ 12, 13, 14]     [ 22, 23, 24]
```

配对 `[(2,1),(0,2)]` 仅返回 `[212,213,214]`、`[22,23,24]`，不展开四格；Frame 0、配对 `[(2,1)]`、Sample `[3,1,3]` 的独立预期为 `[213,211,213]`。

给定逐对样本选择表及独立结果：

```text
Q = [[1,4,2],       A[i,j] = X[0,i,j,Q[i,j]]
     [0,3,6],
     [5,2,7]]

A = [[  1, 14, 22],
     [100,113,126],
     [205,212,227]]
```

<a id="uc-regression"></a>
### 2.4 最小 UC 回归集

以下全部未执行：**`UC-18`（跨文件复检部分）、`UC-23`、`UC-25` 为 `BLOCKED`（后两项归 M4 扩展层，不阻塞 Core）；`UC-09～13` 对应首版预留的 `FMC` 模式（首版 Core 聚焦单晶与 PA，其余均为 `NOT_RUN`）。**

| 用例 | 归属层 / 阶段 | 样例与请求 | 独立预期 / 拒绝条件 | 规则追踪 |
|---|---|---|---|---|
| UC-01 | Core M3 | H/P（及预留 F）分别解释；类别冲突反例 | 模式 Schema 明确区分，不靠 shape 猜测或越界混读（混合见 D-13） | U-01/U-03 |
| UC-02 | Core M3 | 同 Scan 重复固定方案；尝试后续变更法则/长度/dtype/采样轴 | 固定定义复用，真实变更被旧 Scan 明确拒绝 | U-02/U-04 |
| UC-03 | Core M3 | H 三个异构流组联合回读（含 `f32` `NaN`/`-0.0` 变体） | 与 2.1 样本、符号、dtype、长度及 `f32` 按位逐项一致 | U-04 |
| UC-04 | Core M3 | 同 shape/dtype 的阵元接收与 PA 合成输出 | 接收数据层次可辨识，不互换解释 | U-03/U-04 |
| UC-05 | Core M3 | H′（Frame 0 的 W0 `valid=0`）Frame 0、流清单 `[W2,W0,W2]` | 流选择及位图保序保重复，无效零填充不跳过，位置/引用正确 | U-08/U-09/U-10 |
| UC-06 | Core M3 | P 完整帧与多束读取 | 一帧一唯一原始位置 `P_n`，不新增逐束原始位置 | U-05 |
| UC-07 | Core M3 | P 束 `[2,0,2]` 及样本 `[1,4)` | 数值与 `P1/G/L2、P1/G/L0、P1/G/L2` 与 2.2 一致 | U-03/U-05/U-10 |
| UC-08 | Core M3 | 不定位读 P；派生束位置覆盖 `P_n` 反例 | 原始读取成立，拒绝覆盖 `P_n` | U-05/U-12 |
| UC-09 | Core（FMC 预留） | F 全矩阵（打乱流目录）＋ 2.3 五类映射反例 | 9 对按 π 正确；覆盖缺口/别名/悬空/TxRx 冲突明确拒绝 | U-06/U-07；FMC-01/02 |
| UC-10 | Core（FMC 预留） | F 固定 Tx 行、Rx 列、有序子矩阵 | 与 2.3 子矩阵逐值一致，保留轴序与重复项 | U-06/U-09 |
| UC-11 | Core（FMC 预留） | F 配对及互易对分别读取 | 两对不展开四格，互易对独立 | U-06/U-09 |
| UC-12 | Core M3 / 预留 | H `[3,4)` 越界与 Sample `[3,1,3]`；F 给定 Q | H W1 越界整调用拒绝；有序样本保序重复；Q 等于 2.3 A | U-04/U-09 |
| UC-13 | Core（FMC 预留） | F 矩阵/逐流对照；异构及不同时间解释变体 | 同构等效；异构保原表示；同 shape 不冒充共同时间轴 | U-04/U-07 |
| UC-14 | Core M3 | P 分析/Batch（连续与离散清单）、`poll`/`push` 对照及重读 | 数值/关联一致；遵循 `BUF-01` 借用期与两阶段 `push` 原子性；容量查询不失效 `poll` | U-11；READ-03/BUF-01 |
| UC-15 | Core M3 | 有效全 0/非零、无效省略/忽略、LSB-first 尾部位非零、位图缺失、损坏反例 | 单一位图，真实全 0 保真、无效零填充；缺失或尾部位错整批拒；故障不转无效位 | U-08/U-12 |
| UC-16 | Core M3 | 重复位置不同帧；封存后关闭重开重放 | 不合并帧，结果不变，源文件不改写 | U-10/U-12 |
| UC-17 | Core M3 | 2.5 W 四个 Scan（局部 `n/k` 重复、跨 Scan 异构） | 中立容器独立枚举/读取，不隐式融合或覆盖旧 Scan | U-03/U-04/U-13/U-14；SCAN-01 |
| UC-18 | Core M3 / 后置 | 文件内轻量 M:N `Region` 与复检来源（M2 定字段名）；跨文件复检（**BLOCKED** 待 `D-19`） | 拒悬空 Region/Scan 引用；多 Scan 共享 Region 保持独立身份 | REL-01/SCAN-02、D-11/D-19 |
| UC-19 | Core M3 | 顺序完成 W 各 Scan、封存及空 Scan/空文件/非法追加反例 | 拒正常 0 帧完成与 0-Scan 封存；拒向已完成/已封存文件追加；保留空 `Region` 合法性 | U-12/U-13；LIF-01/02 |
| UC-20 | Core M3 / 预留 | 全波与混合保留＋`EndStatus`/空 `Region` 重开（`FeatureOnly` 首版预留） | 按保留交付，不可用依赖明示，不虚构波形或覆盖仅特征采集 | RET-01、D-16 |
| UC-21 | Core M3 | 无空间位置、位置失败（`pos_valid=0`）保全有效波形、同步等级与可选 `CellCoord` 无归属位 | 波形保全，不靠 `NaN` 猜无效或写假零坐标；列式 `nullable` 附加记录准确表达缺值 | POS-01/02、D-01 |
| UC-22 | Core M3 | 单晶/PA 独立 Schema、最小解码核、DICONDE/NeXus 可选物理表、参数化曲面几何与 `VendorExtension` | 模式独立可辨识，不依赖 UMS/目录或点云即可解释 | REL-01、D-09 |
| UC-23 | **扩展层 M4** | 3D 旁路空间索引按 `(x,y,z)` 查出 `0~N` 候选并按指定策略选代表（Core 另验 `0~N` 与 `CellCoord`） | **BLOCKED**：待 `D-17` 扩展层接口与策略配置合同（不阻塞 Core M3） | ACCESS-01、D-17 |
| UC-24 | Core M3 | 封存前伴生快照读与来源追溯；封存后原地修改拒绝；离线派生写 Write-Once 旁路容器（UUID+ScanID 绑定）与原子 `rename` 写失败保旧 | 读不重算且来源不变；原始与旁路均 Write-Once 不可原地改写；失败保旧成果 | SNAP-01、LIF-01、D-16 |
| UC-25 | **扩展层 M4** | 独立选峰扩展：文件输入区域窗口峰峰值与前沿位置/时间+幅值提取 | **BLOCKED**：前沿判据等用户算法参考（`D-18`，不阻塞 Core M3） | MEAS-01、D-18 |
| UC-26 | Core M3 | Core 规范数据子集（Scan / 离散单元区域 / 通道声束 / 样本窗口） | 保留解释、状态与来源；多 Scan 独立；不附带导出打包 | ACCESS-01、D-11 |
| UC-27 | Core M3 | **跨系统外部创建与完整读取**：外部系统经 C ABI 创建独立文件，第三方不依赖 UMS/DB 凭 SDK（含 HDF5 1.14 独立读取器）完整读取 | 验证 `ADR-0015～0020` 跨系统交付与 SDK 独立自解释闭环 | BUS-01、ID-01、R-20；D-07/D-09 |

#### UC-05 的混合有效性素材

H′ 与 H 相同，只把 Frame 0 的 W0 写为 `valid=0` 并省略其输入。Frame 0、流清单 `[W2,W0,W2]` 的独立预期为：W2 `[-2147483648,-1,0,65536,2147483647]`（i32，位 1）、W0 `[0,0,0,0]`（u8 零填充，位 0）、W2 同第一项（位 1）；三项均关联 P0 及各自的事件/接收输出。

#### UC-14 的两种读取交付、离散清单与缓冲素材

以 P 的 Frame 0、1 作为 B=2 的 Batch，样本数为 `2×3×8=48` 个 u16（96 字节波形量）。另增离散清单 `[1, 0, 1]` 变体，核对保序保重复且内部按块合并解码不重复读盘。

对相同选择分别通过 `poll` 和 `push` 读取：
- `poll` 在借用期内与独立期望比对；按 `BUF-01` 借用结束条件（同 Reader 下一次样本/位置/帧记录读取开始，含失败与参数拒；或 Reader 关闭），旧视图到期（`.NET` 绑定通过代数令牌抛出确定异常）；目录、元信息、块几何与容量查询不使其到期；另一 Reader 不影响它。
- `push` 核对关闭 Reader 后内容仍可用、容量不足或损坏时目标逐字节不变（两阶段读）；超过 2 GiB Batch 在 `.NET` 经非托管指针接口验证。

#### UC-15 的单一有效性与零填充素材

在单晶/PA（或预留 F）变体中，构造三个槽位（如 `(0,0)`、`valid=1` 全 0；`(0,1)`、`valid=0` 省略输入；`(0,2)`、`valid=1` 非零 `[20..27]`），核对 LSB-first packed bitset 逻辑有效序列 `[1,0,1]` 与尾部位清零校验：
- `(0,1)` 在 `valid=0` 下提供 `[900..907]` 时，默认零填充，开启 Writer/Scan 级严格模式时整调用拒绝；
- 位图缺失、字节长度不符、尾部位非零或流身份不匹配时整调用拒绝、提交前缀不变；
- 存储损坏或 `XXH3-64` 失败绝不降格为 `valid=0`。

<a id="multi-scan-fixture"></a>
### 2.5 多 Scan 容器样例 W

W 是独立于 H/P/F 的多 Scan 容器语义素材，全部采用单晶模式。四个 Scan 顺序创建，各有两个 Frame（n=0、1）和一条局部名称均为 `k0` 的流，固定定义独立，`valid=1`。

| Scan | Scan 内帧位置关联标记 | k0 dtype / 长度 | Frame 0 / Frame 1 样本 |
|---|---|---|---|
| A | P_A0 / P_A1 | u16 / 3 | `[10,11,12]` / `[13,14,15]` |
| B | P_B0 / P_B1 | u16 / 3 | `[20,21,22]` / `[23,24,25]` |
| C | P_C0 / P_C1 | u16 / 3 | `[30,31,32]` / `[33,34,35]` |
| D | P_D0 / P_D1 | u8 / 4 | `[40,41,42,43]` / `[44,45,46,47]` |

独立预期：A/B/C/D 各自 `N=2`、跨 Scan 重复 `n/k` 互不冲突；按显式 `[B, A, D]` 请求各自保留独立来源与位置；重复 Scan ID、跨 Scan 引用定义、正常 0 帧完成 Scan、正常 0-Scan 封存、向已完成 A 追加、在 B 活动时建新 Scan、向已封存文件追加 E 均拒绝（`LIF-01`、`ADR-0018`）。

## 3. 需求—规则—用例追踪

除 `T-08` 为 **SUPERSEDED（已替代，非 PASS）** 外，以下活动项全部 **`NOT_RUN`**。

| 用例 | 需求 | Spec 规则 | 样例/操作与预期 | 依赖与边界 |
|---|---|---|---|---|
| T-01 | [R-01](DESIGN.md#r-01)、[R-11](DESIGN.md#r-11) | [DOC-01](DATA_SPEC.md#doc-01)、[ID-01](DATA_SPEC.md#id-01)、[VAL-01](DATA_SPEC.md#val-01) | 已知/未知 `format_major`、容器角色、UUID、模式 Schema 与版本解耦拒绝规则 | D-07 M2 wire 编码 |
| T-02 | [R-02](DESIGN.md#r-02)、[R-03](DESIGN.md#r-03) | [REC-01](DATA_SPEC.md#rec-01)、[MAP-01](DATA_SPEC.md#map-01)、[WRT-01](DATA_SPEC.md#wrt-01) | H/P（及预留 F）同步写入与单帧/Batch 读取，可配置 `(F,K,S)` 分块关联一致 | UC-01/05/06/14 |
| T-03 | [R-05](DESIGN.md#r-05) | [WAV-01](DATA_SPEC.md#wav-01)、[WAV-02](DATA_SPEC.md#wav-02) | 有效缺波形、`S_k±1`/错 dtype（含 `f64`/复数拒收）/错位图关联整批拒绝 | UC-02/03/15 |
| T-04 | [R-02](DESIGN.md#r-02)、[R-05](DESIGN.md#r-05) | [WAV-01](DATA_SPEC.md#wav-01)、[WAV-02](DATA_SPEC.md#wav-02) | 整数 `{i8..u32}` 极值与 `f32`（`NaN` payload / `-0.0`）按位无损保真、字节序数值保真 | UC-03/04；ADR-0019 |
| T-05 | [R-05](DESIGN.md#r-05) | [STA-01](DATA_SPEC.md#sta-01) | LSB-first packed bitset、尾部位清零校验、有效全 0 保真、`valid=0` 零填充与严格模式 | UC-15；ADR-0019 |
| T-06 | [R-04](DESIGN.md#r-04) | [READ-01/03](DATA_SPEC.md#read-01)、[BUF-01](DATA_SPEC.md#buf-01)、[META-01](DATA_SPEC.md#meta-01) | 分析/连续与离散 Batch、`poll`/`push` 对照、容量查询不失效借用、元信息关联 | UC-05/07/14/15 |
| T-07 | [R-03](DESIGN.md#r-03)、[R-04](DESIGN.md#r-04) | [POS-01/02](DATA_SPEC.md#pos-01)、[PA-01](DATA_SPEC.md#pa-01)、[ID-02](DATA_SPEC.md#id-02) | PA 唯一帧位置、`pos_valid`、同步等级、`CellCoord` 无归属位、`required`/`nullable` 附加记录 | UC-06～08/16/17/21 |
| T-08 | [R-11](DESIGN.md#r-11) | [PAR-02](DATA_SPEC.md#par-02) | 旧动态快照与 offsets 用例已替代（SUPERSEDED，非 PASS） | 并入固定引用 UC-02/05/07 |
| T-09 | [R-02](DESIGN.md#r-02)、[R-11](DESIGN.md#r-11) | [WAV-01](DATA_SPEC.md#wav-01)、[PAR-01](DATA_SPEC.md#par-01) | 定义真实变更被旧 Scan 拒绝；预定程序循环允许 | UC-02 |
| T-10 | [R-04](DESIGN.md#r-04) | [READ-01](DATA_SPEC.md#read-01)、[READ-02](DATA_SPEC.md#read-02) | 空选择与局部越界整体拒绝、离散帧清单按块合并去重保序保重复 | UC-12/14；ADR-0019 |
| T-11 | [R-02](DESIGN.md#r-02)、[R-07](DESIGN.md#r-07) | [REC-02](DATA_SPEC.md#rec-02)、[WRT-02](DATA_SPEC.md#wrt-02)、[LIF-01](DATA_SPEC.md#lif-01) | `E_x>N` 不暴露、`E_x<N`/缺失/`XXH3-64` 不符报错；双槽提交唯一权威（全毁判不可恢复） | 逐 Scan 检查；ADR-0018 |
| T-12 | [R-07](DESIGN.md#r-07) | [LIF-01](DATA_SPEC.md#lif-01)、[SNAP-01](DATA_SPEC.md#snap-01) | 顺序完成（拒 0 帧）、伴生快照、Write-Once 封存（拒 0-Scan）、Write-Once 旁路容器与原子 `rename` 替换 | UC-19/24；ADR-0017/0018 |
| T-13 | [R-03](DESIGN.md#r-03)、[R-05](DESIGN.md#r-05) | [WRT-01](DATA_SPEC.md#wrt-01) | 批次中间含非法输入整批拒绝，前缀/历史不变且返回 `NOT_COMMITTED` | 前置校验原子性 |
| T-14 | [R-06](DESIGN.md#r-06)、[R-15](DESIGN.md#r-15) | [IO-01](DATA_SPEC.md#io-01)、[WRT-01/03](DATA_SPEC.md#wrt-01)、[BUF-01](DATA_SPEC.md#buf-01)、U-15 | `push` 两阶段读目标不变、`poll` 不发部分视图且旧借用到期；写失败禁原位重试、旧块 `XXH3-64` 不变、带失败标记封存可读 | 详见 3.1；假后端不作证 |
| T-15 | [R-06](DESIGN.md#r-06)、[R-08](DESIGN.md#r-08) | [WRT-03](DATA_SPEC.md#wrt-03)、[MAP-02](DATA_SPEC.md#map-02)、[LIF-02](DATA_SPEC.md#lif-02)、U-15 | `MAP-02` + 按 Scan SWMR（含数千块多级索引）Flush 后任意时刻进程崩溃原地只读恢复并验通 `XXH3-64`；源文件哈希不变 | 仅保进程崩溃（ADR-0008/0018） |
| T-16 | [R-10](DESIGN.md#r-10) | [ID-02](DATA_SPEC.md#id-02)、[CMP-01](DATA_SPEC.md#cmp-01) | 未知 filter 或不支持参数（含非首版内置编解码）明确报错，不回退零数据 | — |
| T-17 | [R-05](DESIGN.md#r-05)、[R-10](DESIGN.md#r-10) | [CMP-01](DATA_SPEC.md#cmp-01)、[WAV-02](DATA_SPEC.md#wav-02) | `none`、`shuffle+zstd`、`shuffle+lz4` 回读逐值（含 `f32` 按位）一致，覆盖尾块与非整 chunk | ADR-0019 |
| T-18 | [R-09](DESIGN.md#r-09) | [CAP-01](DATA_SPEC.md#cap-01)、[REC-02](DATA_SPEC.md#rec-02) | 超 100 GB、工作集超 RAM、有界 Scan 枚举与块对齐 `push` 连续写/读取 | D-02/D-03；计入全链路预算 |
| T-19 | [R-09](DESIGN.md#r-09) | [REC-02](DATA_SPEC.md#rec-02)、[CAP-01](DATA_SPEC.md#cap-01) | 32 位边界与 u64 极值计数/字节防溢出、单 Frame 超限拒绝 | 单元测试与模拟元数据 |
| T-20 | [R-10](DESIGN.md#r-10) | [CMP-02](DATA_SPEC.md#cmp-02)、[WAV-02](DATA_SPEC.md#wav-02) | GPU `nvCOMP` 完整 `shuffle+zstd`/`shuffle+lz4` 解压与 CPU 对照＋端到端测量 | D-06；可选 M4 |
| T-21 | [R-11](DESIGN.md#r-11)、[R-13](DESIGN.md#r-13) | [META-01](DATA_SPEC.md#meta-01)、[ID-02](DATA_SPEC.md#id-02)、[REL-01](DATA_SPEC.md#rel-01)、[VAL-01](DATA_SPEC.md#val-01) | 最小解码核、DICONDE/NeXus 可选物理表、参数化曲面几何与 `VendorExtension` 关联核对 | UC-22、D-09 |
| T-22 | [R-01](DESIGN.md#r-01)、[R-04](DESIGN.md#r-04)、[R-11](DESIGN.md#r-11)、[R-20](DESIGN.md#r-20) | [BUS-01](DATA_SPEC.md#bus-01)、[DOC-01](DATA_SPEC.md#doc-01)、[ID-01](DATA_SPEC.md#id-01)、[VAL-01](DATA_SPEC.md#val-01) | 不依赖 UMS/DB，经 C11 ABI 外部创建并凭独立读取器（含 HDF5 1.14 链接构建）完整互读与拒未知必要能力 | UC-27、D-07/D-09 |
| T-23 | [R-01](DESIGN.md#r-01)、[R-12](DESIGN.md#r-12) | [SCAN-01/02](DATA_SPEC.md#scan-01)、[READ-01](DATA_SPEC.md#read-01)、U-14 | W 多 Scan 身份、文件内 M:N `Region` 独立结果与拒绝反例 | UC-17/18(文件内)/19 |
| T-24 | [R-14](DESIGN.md#r-14) | [CORE-01](DATA_SPEC.md#core-01)、[BUF-01](DATA_SPEC.md#buf-01)、U-16 | 多线程 HDF5 全局串行、多 Reader 独立、多进程只读、写期间同/跨进程（含禁用 HDF5 文件锁）自检拒绝 Reader | `.NET` `SafeHandle`/GC 另见 SDK_CONTRACT |

<a id="risk-verification"></a>
### 3.1 M2 冻结前关键机制取证与 M3 完整覆盖

| 现有追踪 | M2 冻结前优先取证 | M3 完整覆盖与限制 |
|---|---|---|
| T-15 多级索引 SWMR 崩溃 | **核心门禁**：单 Scan 数千块（多级 B-tree）的 `MAP-02 + SWMR` 随机 SIGKILL + Scan 间非 SWMR 切换短窗公开只读 VFD 原地恢复（源文件哈希不变） | 覆盖追加/Flush/完成/伴生快照/封存全阶段故障点（不测断电） |
| T-14 写失败与读原子 | 真实 HDF5 跨对象写失败隔离、禁原位重试、双槽提交全毁判不可恢复；`push` 两阶段读哨兵不变与 `XXH3-64` 开销实测 | 覆盖延迟错误、清理再失败、`seal_with_failure` 与带失败标记读取 |
| T-12 生命周期与旁路 | 拒绝正常 0 帧 Scan/0-Scan 封存；合法保留未采集空 `Region`；Write-Once 旁路容器临时文件 + 原子 `rename` 写失败保旧 | 正常/异常关闭、重复调用与 `H5Fclose` 前崩溃转恢复 |
| T-06/T-14 `.NET` 绑定 | 原生 `COMMITTED` 与托管封装异常隔离；`SafeHandle` 确定性释放；代数令牌受检 `poll`；非托管指针 >2 GiB `push` | Linux `.NET 10` 先闭环，再补 Windows MSVC + `.NET Framework 4.8` 与 `abidiff` |
| T-07/UC-21 位置与列式 | 波形有效×`pos_valid`×同步等级×`CellCoord` 无归属位×`required`/`nullable` 附加记录组合正反例 | 核对提交/封存/恢复一致，不支持晚到补写 |
| T-18/T-19 资源 | 真实 Frame 规模＋`Batch-of-SoA` 全链路峰值预算可行性（最大合法与略超限请求） | 超 100 GB 且工作集超 RAM，按实测校准块几何与 `zstd` 级别 |

## 4. 场景证据转验证与独立检查器

<a id="scenario-validation"></a>
算法输出与存储符合性分开验证；若设备证据与当前契约冲突，须先修订 `DESIGN.md`、`DATA_SPEC.md` 与 `SDK_CONTRACT.md`。建议实现与写入路径解耦的独立只读检查器（含 HDF5 1.14 构建版本），按“识别 → 结构 → 关联 → 深度（有界批次逐块 `XXH3-64`）”分层验证，明确输出失败规则与未检查项。

性能测量必须与逻辑语义分离（历史 micro-benchmark 局限见 [SCENARIO_AUDIT.md#historical-benchmark-limits](SCENARIO_AUDIT.md#historical-benchmark-limits)）：保留 `none` 对照、固定输入比较 `(F_chunk, K_chunk, S)`、区分 OS 热缓存与冷盘带宽、使用真实波形＋不可压缩压力输入、完整记录环境与版本。

<a id="milestones"></a>
## 5. 推进里程碑与 Core 首版验收门禁

| 里程碑 | 交付物 | 完成判据 | 当前状态 |
|---|---|---|---|
| **M0** | 需求收敛、数据契约与工程合同定型 | 确立两层架构、首版范围、业务模型、`MAP-02`+SWMR、编码 Profile、C++20/C11/`.NET` 与版本门禁（`ADR-0001～0020`） | **已完成定型**；待补 `D-02`/`D-09` 真实设备字段与上限事实进入 M2 |
| **M1** | 局部机制原型与进程崩溃/读原子探针 | 取得 `MAP-02` 写入保护、无 `fsync` 进程崩溃、两阶段 `push` 与 1.14 可读初步证据 | **历史局部实验完成**（[M1 报告](../experiments/m1/REPORT.md)，仅覆盖旧单 PA 流组，不重跑、不替代产品验收） |
| **M2** | HDF5 Wire 1.0 规范、`uss.h` C11 头文件、多级索引崩溃取证与 1.14 独立互读样例 | wire 编码与 `uss.h` 无 `TBD`；完成数千块级 `MAP-02 + SWMR` SIGKILL 验证（`D-05`）；外部经 C11 写出并由 1.14 独立读取器验通（`T-22`/`UC-27`） | **下一阶段** |
| **M3** | **SDK Core 首版实现与全面验收** | C++20 核心 + 静态自包含单库 + `.NET`（`net10.0`/`net48`）绑定；Linux x64 闭环 + Windows MSVC/`net48` 实测；覆盖单晶/PA、伴生与旁路快照、>100 GB 超 RAM 与故障恢复门禁 | 未执行 |
| **M4** | **独立扩展层、Python 绑定与可选加速** | 3D 旁路空间索引/多回波扩展（`UC-23`/`D-17`）、窗口选峰扩展（`UC-25`/`D-18`）、官方 Python 绑定、GPU `nvCOMP` 直接解压（`T-20`/`D-06`），及按需展开 `FeatureOnly`/`FMC` | 未执行；**不阻塞 Core M3** |

<a id="core-acceptance"></a>
### Core 首版（M3）验收门禁

本门禁对应 **SDK Core 首版（单晶 + 相控阵 + 伴生/旁路快照，C11 ABI + `.NET`）**；独立扩展层（`UC-23`/`UC-25`）、Python 官方绑定、GPU 解压与预留 `FMC`/`FeatureOnly` 归 M4，不阻塞 Core M3 通过。

| 验收面 | 通过所需证据 | 复用追踪 |
|---|---|---|
| 数据、模式与关联 | `H/P/W`（含 `f32` 按位与列式位置/`CellCoord`）、单晶/PA 独立 Schema、轻量 M:N `Region`、最小解码核＋可选物理表与 `EndStatus` 正确 | UC-01～08/14～22/26、T-02～11/T-21/T-23 |
| 输入、越界与容量拒绝 | 非法批次修改前拒绝（`NOT_COMMITTED`）；空选择与局部越界整体拒绝；u64 溢出与单 Frame 超限显式报错 | T-03/T-10/T-13/T-19 |
| I/O 与原子性 | 真实 HDF5 下两阶段 `push` 目标不变、`poll` 不发部分视图；写失败禁原位重试、旧块 `XXH3-64` 不变、`seal_with_failure` 可读 | T-14、UC-14、3.1 |
| 生命周期、快照与恢复 | 拒正常空 Scan/空文件；伴生快照读与来源不变；Write-Once 旁路容器原子 `rename` 保旧；`MAP-02 + SWMR` 多级索引崩溃原地只读恢复（源文件哈希不变） | T-12/T-14/T-15、UC-19/24 |
| 格式互通与编解码 | `none`/`shuffle+zstd`/`shuffle+lz4` 逐值一致；经 C ABI 外部创建并由 HDF5 1.14 独立读取器完整互读，拒未知必要能力 | T-01/T-16/T-17/T-22、UC-27 |
| 原生静态单库与 `.NET` 绑定 | Linux x64 + Windows 10+ MSVC 静态自包含单库（隐藏内部符号）；`.NET 10` & `.NET 4.8` `SafeHandle`/代数令牌受检 `poll`/>2 GiB 非托管 `push`；`1.0` 起启用 SONAME/符号版本/`abidiff` 门禁 | T-06/T-14/T-24、UC-14；`SDK_CONTRACT.md` |
| 规模与负载 | 超 100 GB 且工作集超 RAM；全链路峰值预算与块对齐 `Batch-of-SoA` 负载门槛达标 | T-18/T-19；D-02/D-03/D-04 |
| 可复核交付 | Spec/实现/样例修订、环境、独立期望、原始结果与已知限制一致 | VAL-01 |
