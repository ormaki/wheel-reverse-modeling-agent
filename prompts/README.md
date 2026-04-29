# 提示词资产

该目录用于管理“按阶段生成轮毂模型”的提示词文件。

规则：

- 一个阶段对应一个提示词文件。
- 一个阶段对应一个主要模型产物。
- 提示词与输出模型必须能够一一追溯。
- 不要直接复用旧的 handoff 文档内容充当阶段提示词。
- 新线程统一从 `NEW_THREAD_PROMPT.md` 开始。

当前阶段划分：

- Stage 01：轮辋轮心回转体创建
- Stage 02：轮心 PCD 孔创建
- Stage 03：轮心凹槽创建
- Stage 04：辐条生成

建议产物目录：

- `output/stages/01/`
- `output/stages/02/`
- `output/stages/03/`
- `output/stages/04/`

当前启用文件：

- `TEMPLATE.md`
- `STAGE_INDEX.md`
- `01_revolve_body_prompt.md`
- `02_pcd_holes_prompt.md`
- `03_hub_grooves_prompt.md`
- `04_spokes_prompt.md`
- `NEW_THREAD_PROMPT.md`
