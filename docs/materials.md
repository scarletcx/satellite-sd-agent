# 卫星总体设计助手 — 素材与开源资源清单

> - 整理时间：2026-10-05，仓库状态（星标 / 是否归档 / 最近提交 / 许可证）均经 GitHub API 实时核实。
> - 配套的可执行下载清单见 [collection-checklist.md](./collection-checklist.md)。
> - 本清单只收集**公开可获取**的资料。标注 🔒 的为受版权保护资料，仅限本地研究阅读，禁止入库再分发。使用前请以各来源官方许可声明为准。

## 目录

- [1. RAG 语料（公开）](#1-rag-语料公开)
- [2. 开源项目](#2-开源项目)
- [3. 缺口清单（需自建）](#3-缺口清单需自建)
- [4. 许可与合规注意](#4-许可与合规注意)
- [5. 状态核实说明](#5-状态核实说明)

---

## 1. RAG 语料（公开）

### 1.1 系统工程与总体设计

| 资料 | 内容 / 用途 | 链接 | 备注 |
|---|---|---|---|
| NASA Systems Engineering Handbook (SP-2016-6105 Rev2) | 总体设计流程、阶段划分、评审门禁 | <https://www.nasa.gov/reference/systems-engineering-handbook/> | 免费 PDF |
| NASA Risk Management Handbook (SP-2011-3422) | 风险识别 / 评估 / 缓解方法论，风险分析模块的骨架 | <https://www.nasa.gov/wp-content/uploads/2023/08/nasa-risk-mgmt-handbook.pdf> | 免费；v2 见 NTRS 20240014019 |
| NASA LLIS 经验教训库 | 数十年真实工程失败与教训，FMEA / 风险分析语料 | <https://llis.nasa.gov/> | 公开检索 |
| Basics of Space Flight (JPL) | 航天基础培训教材 | <https://science.nasa.gov/learn/basics-of-space-flight/> | 免费 |
| MIT OCW 16.851 Satellite Engineering | 分系统设计与工程权衡全套讲义（含作业范例） | <https://ocw.mit.edu/courses/16-851-satellite-engineering-fall-2003/> | CC BY-NC-SA |
| Space Systems Engineering 课程笔记 | 系统工程课程材料（GitHub） | <https://github.com/kyleniemeyer/space-systems-notes> | BSD-3 |
| NASA 技术标准系统 | GSFC-STD-7000（GEVS）等环境试验标准 | <https://standards.nasa.gov/> | 公开 |

### 1.2 小卫星总体 / 分系统 / 选型

| 资料 | 内容 / 用途 | 链接 | 备注 |
|---|---|---|---|
| NASA State-of-the-Art Small Spacecraft Technology（SST-SOA） | 年度更新；各分系统技术现状、选型建议、器件表格。**选型知识库的骨架** | <https://www.nasa.gov/smallsat-institute/sst-soa/> | 免费；年度 PDF 见官网 |
| CubeSat 101 | 首次开发者入门：流程、验证、发射途径 | <https://science.nasa.gov/wp-content/uploads/2023/06/nasa_csli_cubesat_101_508.pdf> | 免费 PDF |
| Cal Poly CubeSat Design Specification Rev14.1 | 1U–12U 外形 / 质量 / 质心 / 抑制要求 | <https://www.cubesat.org/cds-announcement> | 免费；NASA 镜像有 Rev14 |
| eoPortal | ESA 的卫星任务库：平台、载荷、轨道参数 | <https://www.eoportal.org/satellite-missions> | 公开网页 |
| CEOS EO Handbook | 对地观测卫星 / 载荷 / 测量能力数据库 | <https://database.eohandbook.com/> | 公开 |
| Nanosats Database | 全球立方星 / 纳卫星任务与统计数据 | <https://www.nanosats.eu/database> | 公开 |
| cubesat-resources.space | 社区整理的标准、教程、硬件资料目录 | <https://cubesat-resources.space/> | CC0 |
| NASA S3VI 小卫星任务设计工具清单 | NASA 官方整理的公开工具索引（下文多处引用） | <https://www.nasa.gov/smallsat-institute/space-mission-design-tools/> | 公开 |

### 1.3 测控数传与链路

| 资料 | 内容 / 用途 | 链接 | 备注 |
|---|---|---|---|
| JPL DSN Telecommunications Link Design Handbook (810-005) | 链路预算方法学、天线 / 调制 / 编码参数 | <https://deepspace.jpl.nasa.gov/dsndocs/810-005/> | 免费；逐模块下载 |
| NASA Near Earth Network (NEN) Users' Guide | 地面站能力、频段、接口参数 | <https://ntrs.nasa.gov/citations/20205005784> | 免费 |
| CCSDS Blue Books | 遥测遥控、数据链路、射频调制等推荐标准 | <https://ccsds.org/publications/bluebooks/> | 免费 |
| ITU-R 建议书 | 频率划分、传播模型、干扰保护 | <https://www.itu.int/pub/r-rec> | 免费 |
| 🔒 天线 / 通信系统教材 | 公式推导与例题（如《卫星通信》类教材） | （线下 / 图书馆） | 版权保护，仅本地参考 |

### 1.4 运载与发射

| 资料 | 内容 / 用途 | 链接 | 备注 |
|---|---|---|---|
| SpaceX Falcon User's Guide (2025) | 包络、质量能力、力学环境、适配器 | <https://www.spacex.com/assets/media/falcon-users-guide-2025-05-09.pdf> | 公开 PDF |
| Ariane 6 User's Manual | 同上（欧洲火箭） | <https://www.ariane.group/app/uploads/sites/4/2024/10/Mua-6_Issue-2_Revision-0_March-2021.pdf> | 公开 PDF |
| 其他运载 | 各大运载均发布公开 User's Guide，可按任务补充 | — | — |

### 1.5 标准体系

| 标准体系 | 覆盖范围 | 链接 | 备注 |
|---|---|---|---|
| ECSS（欧空局） | 总体、电源、热、结构、软件、项目管理全套 | <https://ecss.nl/standards/> | 免费下载，接受免责声明 |
| CCSDS | 空间数据系统、遥测遥控、射频调制 | <https://ccsds.org/publications/bluebooks/> | 免费 |
| ITU-R | 频谱 / 轨道资源、传播 | <https://www.itu.int/pub/r-rec> | 免费 |
| NASA 技术标准 | 各中心标准（GEVS 等） | <https://standards.nasa.gov/> | 公开 |
| 🔒 AIAA / ISO / GJB 标准 | 部分付费，不可公开分发 | — | 按需购买或本地查阅 |

### 1.6 数据与统计（做校验基准与合成语料）

| 数据源 | 内容 | 链接 | 备注 |
|---|---|---|---|
| UCS Satellite Database | 数千颗卫星的质量 / 功耗 / 寿命 / 轨道 / 用途 | <https://www.ucs.org/resources/satellite-database> | 季度更新，CSV/XLSX |
| GCAT（Jonathan McDowell） | 全球航天器编目与发射记录 | <https://planet4589.org/space/gcat/> | 公开 |
| NSSDCA | NASA 空间科学数据与任务档案 | <https://nssdc.gsfc.nasa.gov/> | 公开 |
| NTRS | 50 万+ 索引、20 万+ 全文（型号设计报告主力语料） | <https://ntrs.nasa.gov/> | 公开；支持批量 harvest |
| NASA Software | 1000+ NASA 免费软件（含成本模型 PCEC、星座工具 TAT-C 等） | <https://software.nasa.gov/> | 免费，许可需确认 |

### 1.7 中文语料

| 资料 | 内容 | 链接 | 备注 |
|---|---|---|---|
| 《2021 中国的航天》白皮书 | 国家航天政策、空间基础设施、测控体系 | <https://www.gov.cn/zhengce/2022-01/28/content_5670920.htm> | 政府公开 |
| 北斗 ICD（空间信号接口控制文件） | B1I / B3I 等公开服务信号规范 | <http://www.beidou.gov.cn/xt/gfxz/201902/P020190227592987952674.pdf> | 官方唯一发布渠道 |
| 中国资源卫星应用中心资料下载 | 高分 / 资源系列卫星用户手册、数据规范 | <https://www.cresda.cn/zgzywxyyzx/zlxz/list/index_pc_1.html> | 公开 |
| 国家航天局 | 任务与工程公开信息 | <https://www.cnsa.gov.cn/> | 公开 |
| 🔒 知网 / 万方 / 中文教材 | 学位论文、型号设计文献 | — | 有版权，仅本地阅读，禁止入库 |

### 1.8 批量获取与合成语料策略

- **NTRS**：优先用检索 + harvest 接口按主题（如 "small satellite design report"、"mission concept"）批量拉取；入库时保留原始链接与许可证字段。
- **网站类语料**（eoPortal / Nanosats / CEOS）：抓取前确认 robots 与使用条款，控制频率。
- **中文缺口**：公开中文工程文档少，建议"白皮书 + ICD + 用户手册"打底，其余用 LLM 合成"型号总体设计报告 / 测控方案 / 评审意见"样例，**逐份标注 `synthetic=true`**，并在 manifest 中记录生成方式与时间。

---

## 2. 开源项目

> 状态标记：`★ 星标 · 最近提交 · 许可证`。许可证为 AGPL / GPL 的项目，参考设计可以，**不要直接嵌入你的代码**。

### 2.1 轨道动力学 / 传播 / 任务分析（最成熟的一类）

| 项目 | 说明 | 状态与链接 |
|---|---|---|
| poliastro | 经典 Python 天体动力学库 | ⚠️ 已归档（2023-10 停维），勿作长期底座 · <https://github.com/poliastro/poliastro> |
| Nyx | 高精度天体动力学工具包（Rust，Python 绑定） | 495★ · 活跃 · AGPL-3.0 · <https://github.com/nyx-space/nyx> |
| Basilisk | 航天器动力学 / 姿态 / 硬件在环全仿真框架 | 400★ · 活跃 · ISC · <https://github.com/AVSLab/basilisk> |
| Tudat (tudatpy) | TU Delft 天体动力学工具箱 | 92★ · 活跃 · BSD-3 · <https://github.com/tudat-team/tudatpy> |
| Orekit | 工业级低层空间动力学库（Java） | 301★ · 活跃 · Apache-2.0 · <https://github.com/CS-SI/Orekit> |
| GMAT | NASA 通用任务分析工具 | 121★ · 活跃 · Apache-2.0 · <https://github.com/nasa/GMAT> |
| PyKEP | ESA 星际轨迹设计与优化 | 426★ · 活跃 · MPL-2.0 · <https://github.com/esa/pykep> |
| brahe | 面向工程的实用天体动力学库 | 103★ · 活跃 · MIT · <https://github.com/duncaneddy/brahe> |
| lox | Oxidized Astrodynamics（Rust） | 387★ · 活跃 · MPL-2.0 · <https://github.com/lox-space/lox> |
| SatMAD | 卫星任务分析与设计（Python） | 50★ · 停更 2023-02 · 许可证不明 · <https://github.com/egemenimre/satmad> |
| orbit-predictor | TLE 传播 / 过境预测（Satellogic） | 151★ · MIT · <https://github.com/satellogic/orbit-predictor> |
| orbdetpy | 定轨（Python） | 129★ · <https://github.com/ut-astria/orbdetpy> |
| AWP | 《Astrodynamics with Python》配套代码与视频 | 427★ · <https://github.com/alfonsogonzalez/AWP> |
| dSGP4 | 可微分 SGP4，便于接入 ML / 批量计算 | 97★ · GPL-3.0 · <https://github.com/esa/dSGP4> |

### 2.2 星座 / 覆盖 / 数传规划

| 项目 | 说明 | 状态与链接 |
|---|---|---|
| SatLib | 星座传播、地面站可见性、星间链路窗口（MIT） | 28★ · <https://github.com/manweichan/SatLib> |
| SPRINT | 星座调度 / 数传规划（MIT STAR Lab） | 45★ · <https://github.com/MIT-STARLab/SPRINT> |
| VCE | 虚拟星座引擎：视线 / 时延 / 带宽仿真 | 6★ · <https://github.com/isi-rcg/vce> |
| keepTrack | 卫星编目与三维可视化 | 1600★ · 活跃 · AGPL-3.0 · <https://github.com/thkruz/keeptrack.space> |
| OpenSpace | 任务三维可视化（适合汇报演示） | 1263★ · 活跃 · <https://github.com/OpenSpace/OpenSpace> |

### 2.3 子系统建模（电源 / 链路 / ADCS / 热）

| 项目 | 说明 | 状态与链接 |
|---|---|---|
| pvlib | 光伏发电建模（改 AM0 参数可用于太阳翼估算） | 1682★ · BSD-3 · <https://github.com/pvlib/pvlib-python> |
| eps-design-tools | 浏览器端电源预算 / 能量平衡 / 电池计算器 | <https://github.com/SunElliot/eps-design-tools> |
| Link-Budget-Toolbox | 模块化 Python 链路预算工具 | 13★ · GPL-3.0 · <https://github.com/LMaiorano/Link-Budget-Toolbox> |
| Optical-Link-Budget | 光通信链路预算（MIT） | 29★ · LGPL-3.0 · <https://github.com/MIT-STARLab/Optical-Link-Budget> |
| SatLink | 链路衰减 / 可用度 / 天线尺寸估算 | 36★ · MIT · <https://github.com/cfragoas/SatLink> |
| pycraf | ITU-R 传播与干扰模型（Python） | 59★ · <https://github.com/bwinkel/pycraf> |
| leo-adcs-simulator | LEO 姿态动力学与磁力矩器仿真 | 32★ · MIT · <https://github.com/leocelente/leo-adcs-simulator> |
| adcs-simulation | ADCS 仿真器 | 36★ · <https://github.com/gavincmartin/adcs-simulation> |
| COTS-Star-Tracker | NASA 开源星敏感器（Python） | 122★ · BSD-3 · <https://github.com/nasa/COTS-Star-Tracker> |
| Open Star Tracker | 开源星跟踪器（SPEL，飞行验证） | 95★ · GPL-3.0 · <https://github.com/spel-uchile/Star_Tracker> |
| Quetzal-1 FSW | 飞行验证的 EPS / ADCS 飞行软件 | 60★ · <https://github.com/Quetzal-1-CubeSat-Team/quetzal1-flight-software> |
| quicksat | 卫星快速尺寸估算（小型示例） | <https://github.com/egemenimre/quicksat> |
| 热分析 | 零散小脚本（如 thermal transient analysis），无成熟库 | <https://github.com/georgeslabreche/spacecraft-thermal-transient-analysis> |

### 2.4 多学科优化与总体预算

| 项目 | 说明 | 状态与链接 |
|---|---|---|
| OpenMDAO | NASA 开源多学科设计与优化框架（总体参数权衡） | 791★ · 活跃 · <https://github.com/OpenMDAO/OpenMDAO> |
| Dymos | 轨迹优化（基于 OpenMDAO） | 300★ · Apache-2.0 · <https://github.com/OpenMDAO/dymos> |
| matlab-spacecraft-design | 卫星任务设计的 Matlab 工具（参考建模思路） | 11★ · <https://github.com/seakers/matlab-spacecraft-design> |
| Earth-Observation-Satellite-Mission-Design | 对地观测卫星初步设计与验证（Python，含 Monte Carlo，结构可参考） | <https://github.com/mathonwyaj/Earth-Observation-Satellite-Mission-Design> |

> 注意：**整星质量 / 功耗 / 数据量预算的统一工具链没有任何成熟开源实现**，需要用文献经验公式自建（见第 3 节）。

### 2.5 需求追踪 / 风险分析 / 文档生成

| 项目 | 说明 | 状态与链接 |
|---|---|---|
| StrictDoc | 需求管理与双向追溯，可导出文档 | 401★ · 活跃 · <https://github.com/strictdoc-project/strictdoc> |
| Doorstop | Python 需求管理与追溯 | 672★ · 活跃 · <https://github.com/doorstop-dev/doorstop> |
| duvet | 需求覆盖率 / 追溯分析（AWS Labs） | 162★ · Apache-2.0 · <https://github.com/awslabs/duvet> |
| LLMRiskAnalyzer | LLM 辅助 FMEA（风险分析模块直接参考） | 39★ · <https://github.com/YuchenXia/LLMRiskAnalyzer> |
| open-fmea | 开源 FMEA 工具 | 41★ · GPL-3.0 · <https://github.com/dromation/open-fmea> |
| RAMSTK | RAMS（可靠性 / 可用性 / 维修性 / 安全性）分析 | 58★ · BSD-3 · <https://github.com/ReliaQualAssociates/ramstk> |
| docxtpl | Word 模板渲染（占位符 → 正式文档） | <https://github.com/elapouya/python-docxtpl> |
| python-docx | Word 读写底层库 | <https://github.com/python-openxml/python-docx> |

### 2.6 飞控与地面（仅作参考，大概率过重）

| 项目 | 说明 | 状态与链接 |
|---|---|---|
| F Prime | JPL 飞行软件框架 | 11808★ · Apache-2.0 · <https://github.com/nasa/fprime> |
| cFS | NASA 核心飞行系统 | 1520★ · Apache-2.0 · <https://github.com/nasa/cFS> |
| NOS3 | 小卫星运行仿真环境（IV&V） | 637★ · <https://github.com/nasa/nos3> |
| Open MCT | 任务控制可视化框架 | 13152★ · <https://github.com/nasa/openmct> |
| Yamcs | 任务控制中心框架 | 322★ · AGPL-3.0 · <https://github.com/yamcs/yamcs> |
| COSMOS | 指挥控制 / 测试工具 | 253★ · <https://github.com/OpenC3/cosmos> |
| PyCubed | 开源立方星电子学平台 | <https://github.com/pycubed> |

### 2.7 AI + 航天（同类项目与研究）

| 项目 / 论文 | 说明 | 状态与链接 |
|---|---|---|
| ⭐ Space Engineering Pack (devideamax/aerospace-team) | **目前最接近"AI 卫星设计助手"的开源先例**：12 个 Claude Skills 覆盖 mission-architect（质量 / 功耗 / 数据预算、trade study）、卫星通信、电源、GNC、载荷、地面、空间环境等，附 Python 计算工具与 JSON 器件库 | 22★ · 活跃 · MIT+Attribution · <https://github.com/devideamax/aerospace-team> |
| space-copilot (Ayu0922) | ISRO 任务文档 RAG 问答（RAG + ChromaDB + FastAPI 小样例） | <https://github.com/Ayu0922/space-copilot> |
| aerospace-agent (PoseZhaoyutao) | 中文航天 Agent（轨道 / GNC 方向，早期项目） | <https://github.com/PoseZhaoyutao/aerospace-agent> |
| LLMSat | LLM 驱动的自主航天器目标导向 Agent（论文） | <https://arxiv.org/abs/2405.01392> |
| Language Models are Spacecraft Operators | GPT-4 执行自主卫星机动（论文） | <https://arxiv.org/abs/2404.00413> |
| ASTREA | ISS 在轨运行的 LLM Agent（论文） | <https://arxiv.org/abs/2509.13380> |
| 华山大模型（中科天塔） | 国内航天私域大模型，聚焦在轨管理（闭源，仅作行业背景） | <https://www.chinanews.com/gn/2025/05-15/10415749.shtml> |

> 结论：**没有找到"输入任务目标 → 输出可验证整星设计方案"的完整开源实现**。aerospace-team 是形态最接近的参考，但它只有技能与工具集，缺少 RAG 语料、数值校验闭环和文档生成链路。

### 2.8 资源目录（Awesome Lists）

| 目录 | 说明 |
|---|---|
| [awesome-aerospace-engineering](https://github.com/mahran-sayed/awesome-aerospace-engineering)（449★） | 航空航天学习资源总汇 |
| [awesome-open-source-cubesats](https://github.com/parker-research/awesome-open-source-cubesats) | 开源立方星项目目录 |
| [Space-Systems-Engineering-Resources](https://github.com/HaralDev/Space-Systems-Engineering-Resources) | 任务设计资源 / 脚本 / 可视化 |
| [spacecraft-engineering 相关课程仓库](https://github.com/kyleniemeyer/space-systems-notes) | 系统工程课程材料 |

---

## 3. 缺口清单（需自建）

以下模块**没有成熟开源实现**，建议自建（这也是"哪些该程序做、怎么验证"的直接论据）：

1. **整星质量 / 功耗 / 数据量预算工具链**：基于文献经验公式（SMAD 体系）+ 自建余量策略，统一数据结构并支持版本追踪。
2. **跨模块一致性校验引擎**：太阳翼面积 ↔ 功率 ↔ 质量 ↔ 包络 ↔ 姿态能力 ↔ 发射约束的联立检查；预算闭合与余量校验；**这是跨模块一致性校验的核心，开源没有对应实现**。
3. **器件选型知识库**：以 NASA SST-SOA 表格为骨架，补充厂商公开 datasheet 参数（注意授权），支持按约束筛选。
4. **中文型号文档解析与生成**：docxtpl 模板 + 结构化数据渲染；LLM 只写叙述段落，数字全部来自结构化 IR。
5. **数值出处（provenance）机制**：每个数字带 `值 / 单位 / 来源（计算 ID、文档引用、或显式假设）/ 余量 / 待确认标记`。

## 4. 许可与合规注意

- **代码许可证**：MIT / Apache-2.0 / BSD / ISC（brahe、Orekit、GMAT、PyKEP、Basilisk、pvlib、OpenMDAO、Dymos 等）可放心参考；**AGPL-3.0（Nyx、keepTrack、Yamcs）与 GPL 系（dSGP4、Pypredict、Link-Budget-Toolbox、Open Star Tracker、open-fmea）不要直接嵌入闭源代码**。SatMAD 许可证不明。
- **文档许可**：ECSS / CCSDS / ITU-R / NASA 文档可公开获取，各有免责声明与引用要求；🔒 教材、SMAD（Wertz & Larson）、AIAA / ISO / GJB 标准、知网文献**仅本地阅读，禁止入库再分发**。
- **合成语料**：逐份标注 `synthetic=true` 与生成方式，避免后续"来源可追溯"时翻车。
- **存档规范**：下载文件统一登记 manifest（见 checklist），保留原始 URL 与许可证字段。

## 5. 状态核实说明

- 仓库状态通过 `gh api repos/<owner>/<repo>` 于 2026-10-05 核实；星标数为约数，会随时间变化。
- 复核命令示例：

  ```bash
  gh api repos/nyx-space/nyx --jq '{stars: .stargazers_count, archived: .archived, pushed: .pushed_at, license: .license.spdx_id}'
  ```

- 工具/资料的链接如失效，优先在该机构官网检索（NASA 站点改版较频繁）。
