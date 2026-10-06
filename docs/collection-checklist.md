# 采集清单（带下载链接）

> - 用途：照单执行资料采集。详细说明与开源项目状态见 [materials.md](./materials.md)。
> - 优先级：**P0** = 第一批必需；**P1** = 第二批；**P2** = 可选。
> - 🔒 = 受版权保护，仅限本地阅读研究，**禁止入库公开仓库、禁止再分发**。
> - 下载建议：存到 `corpus/raw/<模块>/`，逐条登记到 `corpus/manifest.csv`。

## 使用方法

1. 建目录：

   ```bash
   mkdir -p corpus/raw/{manuals,smallsat,ttc,launch,standards,data,cn,research} corpus/synthetic
   ```

2. 每下载一个文件，计算校验值并登记：

   ```bash
   shasum -a 256 <file>
   ```

3. manifest 字段建议：

   ```csv
   id,module,title,source_url,license,fetched_at,file_name,sha256,synthetic,notes
   ```

4. 网站类资料（eoPortal 等）按需保存为 PDF / Markdown 快照，同样登记 `source_url`。

---

## A. 手册与教材（P0）

- [ ] NASA Systems Engineering Handbook（SP-2016-6105 Rev2）— <https://science.nasa.gov/wp-content/uploads/2023/04/nasa_systems_engineering_handbook_0.pdf>
- [ ] NASA Risk Management Handbook（SP-2011-3422）— <https://www.nasa.gov/wp-content/uploads/2023/08/nasa-risk-mgmt-handbook.pdf>
- [ ] NASA Risk Management Handbook v2（NTRS 页面）— <https://ntrs.nasa.gov/citations/20240014019>
- [ ] Basics of Space Flight（在线教程，可存快照）— <https://science.nasa.gov/learn/basics-of-space-flight/>
- [ ] MIT OCW 16.851 Satellite Engineering 全套讲义 — <https://ocw.mit.edu/courses/16-851-satellite-engineering-fall-2003/download/>
- [ ] NASA LLIS 经验教训（按关键词批量检索导出）— <https://llis.nasa.gov/>
- [ ] 🔒 SMAD / 航天器系统设计类教材 — 仅线下阅读，不入库

## B. 小卫星总体与选型（P0）

- [ ] NASA SST-SOA 年度报告 PDF（官网首页可换最新版）— <https://www.nasa.gov/wp-content/uploads/2026/05/soa-2026.pdf>
- [ ] SST-SOA 各章节网页（逐章保存，含器件表格）— <https://www.nasa.gov/smallsat-institute/sst-soa/>
- [ ] CubeSat 101 — <https://science.nasa.gov/wp-content/uploads/2023/06/nasa_csli_cubesat_101_508.pdf>
- [ ] Cal Poly CubeSat Design Specification Rev 14 — <https://www.nasa.gov/wp-content/uploads/2018/01/cubesatdesignspecificationrev14_12022-02-09.pdf>
- [ ] Cal Poly CDS 最新版本 — <https://www.cubesat.org/cds-announcement>
- [ ] eoPortal 任务库（挑 20~30 个典型型号存档）— <https://www.eoportal.org/satellite-missions>
- [ ] CEOS EO Handbook 数据库 — <https://database.eohandbook.com/>
- [ ] Nanosats Database — <https://www.nanosats.eu/database>
- [ ] cubesat-resources.space（CC0 资料集）— <https://cubesat-resources.space/>
- [ ] NASA S3VI 任务设计工具清单（工具索引）— <https://www.nasa.gov/smallsat-institute/space-mission-design-tools/>

## C. 测控数传与链路（P0）

- [ ] JPL DSN 链路设计手册 810-005（按模块下载）— <https://deepspace.jpl.nasa.gov/dsndocs/810-005/>
- [ ] DSN 810-005 下载页（天线 / 覆盖表格等附件）— <https://deepspace.jpl.nasa.gov/dsndocs/810-005/downloads/>
- [ ] NEN Users' Guide — <https://ntrs.nasa.gov/citations/20205005784>
- [ ] CCSDS Blue Books（优先 131 / 231 / 301 / 320 / 401）— <https://ccsds.org/publications/bluebooks/>
- [ ] ITU-R 相关建议书（如 P 系列传播模型、SA 系列频率）— <https://www.itu.int/pub/r-rec>

## D. 数据与统计（P0）

- [ ] UCS Satellite Database（CSV / XLSX，登记版本日期）— <https://www.ucs.org/resources/satellite-database>
- [ ] GCAT 编目 — <https://planet4589.org/space/gcat/>
- [ ] NSSDCA — <https://nssdc.gsfc.nasa.gov/>
- [ ] NTRS 批量检索（small satellite design report / mission concept 等关键词）— <https://ntrs.nasa.gov/>
- [ ] NTRS harvest 接口 — <https://ntrs.nasa.gov/?method=harvest>
- [ ] NASA Software（成本模型 PCEC、TAT-C 等，按需申请）— <https://software.nasa.gov/>

## E. 运载与发射（P1）

- [ ] SpaceX Falcon User's Guide — <https://www.spacex.com/assets/media/falcon-users-guide-2025-05-09.pdf>
- [ ] Ariane 6 User's Manual — <https://www.ariane.group/app/uploads/sites/4/2024/10/Mua-6_Issue-2_Revision-0_March-2021.pdf>
- [ ] 其他运载 User's Guide（按候选火箭补充）

## F. 标准体系（P1）

- [ ] ECSS 标准（先取 E-ST-10 总体、E-ST-20 电气、E-ST-30 电源、E-ST-31 热、E-ST-32 结构系列）— <https://ecss.nl/standards/>
- [ ] NASA 技术标准（GEVS 等）— <https://standards.nasa.gov/>
- [ ] 🔒 AIAA / ISO / GJB 标准 — 仅按需购买，不入库

## G. 中文公开资料（P1）

- [ ] 《2021 中国的航天》白皮书 — <https://www.gov.cn/zhengce/2022-01/28/content_5670920.htm>
- [ ] 北斗 ICD（B1I 3.0 等）— <http://www.beidou.gov.cn/xt/gfxz/201902/P020190227592987952674.pdf>
- [ ] 中国资源卫星应用中心资料下载（高分 / 资源用户手册）— <https://www.cresda.cn/zgzywxyyzx/zlxz/list/index_pc_1.html>
- [ ] 国家航天局公开信息 — <https://www.cnsa.gov.cn/>
- [ ] 🔒 知网 / 万方学位与型号论文 — 仅本地阅读，不入库

## H. 研究与论文（P2）

- [ ] LLMSat — <https://arxiv.org/abs/2405.01392>
- [ ] Language Models are Spacecraft Operators — <https://arxiv.org/abs/2404.00413>
- [ ] ASTREA（ISS 在轨 LLM Agent）— <https://arxiv.org/abs/2509.13380>
- [ ] Space Engineering Pack（逐文件精读，参考其 skill 结构）— <https://github.com/devideamax/aerospace-team>

## I. 代码仓库克隆（P0/P1）

```bash
mkdir -p vendor && cd vendor

# 轨道动力学 / 任务分析（P0）
git clone --depth 1 https://github.com/AVSLab/basilisk.git        # ISC
git clone --depth 1 https://github.com/tudat-team/tudatpy.git     # BSD-3
git clone --depth 1 https://github.com/duncaneddy/brahe.git       # MIT
git clone --depth 1 https://github.com/satellogic/orbit-predictor.git  # MIT
git clone --depth 1 https://github.com/esa/pykep.git              # MPL-2.0

# 星座 / 覆盖（P1）
git clone --depth 1 https://github.com/manweichan/SatLib.git
git clone --depth 1 https://github.com/MIT-STARLab/SPRINT.git

# 子系统（P1）
git clone --depth 1 https://github.com/pvlib/pvlib-python.git
git clone --depth 1 https://github.com/LMaiorano/Link-Budget-Toolbox.git
git clone --depth 1 https://github.com/leocelente/leo-adcs-simulator.git
git clone --depth 1 https://github.com/nasa/COTS-Star-Tracker.git

# 优化 / 工程配套（P1）
git clone --depth 1 https://github.com/OpenMDAO/OpenMDAO.git
git clone --depth 1 https://github.com/strictdoc-project/strictdoc.git
git clone --depth 1 https://github.com/YuchenXia/LLMRiskAnalyzer.git

# 同类 AI 项目（P0，逐文件精读）
git clone --depth 1 https://github.com/devideamax/aerospace-team.git
```

> AGPL / GPL 仓库（nyx、keepTrack、Yamcs、dSGP4 等）如需参考请单独克隆、单独目录隔离，不要并入主代码。

## J. 合成语料任务（公开来源不足时）

- [ ] 生成 10 份"典型遥感卫星总体设计报告"样例（含构型、分系统配置、质量 / 功耗 / 数据量预算表；`synthetic=true`）
- [ ] 生成 10 份"测控数传方案"样例（含链路预算表、地面站过境计划）
- [ ] 生成 5 份"风险分析与 FMEA"样例（参考 LLIS 真实案例改写）
- [ ] 基于 SST-SOA 表格 + 公开 datasheet 整理器件库 seed（记录来源 URL 与 license）
- [ ] 每份合成文档标注：生成时间、生成方式（模型 + prompt 摘要）、参考的真实来源

## K. 完成后检查

- [ ] manifest.csv 无缺字段，🔒 项未被放入任何公开仓库
- [ ] 随机抽 5 个下载文件打开验证非损坏
- [ ] 目录结构稳定：`corpus/raw/<模块>/`、`corpus/synthetic/`、`corpus/manifest.csv`
- [ ] 全量校验一次：`shasum -a 256 corpus/raw/**/* > corpus/checksums.txt`
