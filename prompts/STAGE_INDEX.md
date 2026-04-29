# 阶段索引

该文件用于统一登记每个阶段的提示词、输出产物、结论和推进状态。

使用规则：

- 每完成一个阶段，就补全对应表格行。
- 如果阶段失败，也要记录失败原因，不要留空。
- 提示词文件、模型文件、记录文件必须能一一对应。
- 只有当前阶段被明确判定为稳定，才能进入下一阶段。

## 阶段总览

| 阶段 | 名称 | 提示词文件 | 主要模型产物 | 记录文件 | 当前状态 | 是否可进入下一阶段 |
|------|------|------------|--------------|----------|----------|--------------------|
| 01 | 轮辋轮心回转体创建 | `prompts/01_revolve_body_prompt.md` | `output/stages/01/01_revolve_body.step` | `output/stages/01/01_revolve_body_notes.md` | 未开始 | 否 |
| 02 | 轮心 PCD 孔创建 | `prompts/02_pcd_holes_prompt.md` | `output/stages/02/02_pcd_holes.step` | `output/stages/02/02_pcd_holes_notes.md` | 未开始 | 否 |
| 03 | 轮心凹槽创建 | `prompts/03_hub_grooves_prompt.md` | `output/stages/03/03_hub_grooves.step` | `output/stages/03/03_hub_grooves_notes.md` | 未开始 | 否 |
| 04 | 辐条生成 | `prompts/04_spokes_prompt.md` | `output/stages/04/04_spokes.step` | `output/stages/04/04_spokes_notes.md` | 未开始 | 否 |

## 阶段记录模板

### Stage 01

- 提示词版本：
- 执行线程：
- 修改文件：
- 输出模型：
- 输出记录：
- 当前结论：
- 失败原因或剩余问题：
- 是否进入 Stage 02：

### Stage 02

- 提示词版本：
- 执行线程：
- 修改文件：
- 输出模型：
- 输出记录：
- 当前结论：
- 失败原因或剩余问题：
- 是否进入 Stage 03：

### Stage 03

- 提示词版本：
- 执行线程：
- 修改文件：
- 输出模型：
- 输出记录：
- 当前结论：
- 失败原因或剩余问题：
- 是否进入 Stage 04：

### Stage 04

- 提示词版本：
- 执行线程：
- 修改文件：
- 输出模型：
- 输出记录：
- 当前结论：
- 失败原因或剩余问题：
- 是否完成整套阶段：
