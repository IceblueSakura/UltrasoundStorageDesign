# UltrasoundStorageDesign

超声采集原始数据存储设计项目。当前已形成逻辑架构和数据 Spec `0.1-draft`，尚未实现生产 SDK、符合性检查器或完整样例。

## 阅读入口

1. [文档索引](docs/README.md)
2. [需求与架构决策](docs/DESIGN.md)
3. [初版数据 Spec](docs/DATA_SPEC.md)
4. [Spec 验证计划](docs/SPEC_TEST_PLAN.md)
5. [历史基准证据与局限](docs/BENCHMARK_REPORT.md)

需求理由、数据契约、验证方法和性能证据分别维护，不以历史脚本默认值补全待定需求。

## 仓库组织

```text
UltrasoundStorageDesign/
├─ README.md                   项目入口
├─ docs/                       当前设计、Spec、测试计划和报告
├─ archive/
│  ├─ README.md                归档说明与保留边界
│  ├─ hdf5/                    既有 HDF5 上游检出，保留嵌套 .git
│  └─ benchmarks/
│     └─ ultrasound_storage_baseline/
│        ├─ benchmark*.py      历史实验脚本
│        ├─ requirements.txt
│        ├─ candidate_catalog.json
│        ├─ MANIFEST.sha256    原历史清单，不是当前校验清单
│        └─ benchmark_results*/ 现存本地结果
├─ flake.nix                   当前开发环境入口
└─ flake.lock                  环境锁
```

[归档说明](archive/README.md)区分上游源码与历史实验。结果、缓存和嵌套仓库继续按原有类别忽略；移动没有使它们自动加入父仓库，也不保证它们随克隆分发。历史 JSON 和 MANIFEST 的内容不改写，记录中的旧路径仅表示当时的运行位置。

未来实现时再创建 `src/`、`tests/`、`tools/` 或 `experiments/`，不预先放置空框架。新的实验源码与可重复的符合性测试不应写入历史归档；生成结果建议使用 `experiments/runs/`，该位置已忽略，不覆盖既往结果。

## 开发环境

从仓库根目录运行：

```bash
nix develop
```

默认环境使用 flake 中声明的 HDF5 构建，不依赖归档检出。可选 `hdf5-local` 源路径已调整为 `archive/hdf5/`。该目录不在父 Git 索引中，若需要本地源码构建，应使用包含工作树的路径 flake，例如 `nix build path:.#hdf5-local`，并确保归档源码存在；Git 源 flake 不包含忽略的本地检出。本次未构建或验证环境运行。

历史脚本的手动运行说明在 [docs/README.md](docs/README.md)，仅用于实验复查，不是生产用法。压缩脚本仍有已记录的覆盖保护缺口，务必选择新的专用输出目录。
