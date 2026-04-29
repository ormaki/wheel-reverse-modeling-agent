# 新线程提示词

请在当前仓库中新开一个 Codex 线程，并且只用于“按阶段生成轮毂模型”的工作。

严格按下面流程执行：

1. 阅读 `prompts/README.md`
2. 阅读 `prompts/TEMPLATE.md`
3. 阅读 `prompts/01_revolve_body_prompt.md`
4. 阅读 `prompts/02_pcd_holes_prompt.md`
5. 阅读 `prompts/03_hub_grooves_prompt.md`
6. 阅读 `prompts/04_spokes_prompt.md`
7. 阅读 `HANDOFF_20260323.md`
8. 阅读 `specs/agent_system_status.md`
9. 只从 Stage 01 开始，不要跳阶段

执行规则：

- 每个阶段都必须同时留下“提示词文件”和“对应模型产物”
- 阶段产物统一存放到 `output/stages/<stage-id>/`
- 不要覆盖 `output/` 里的历史参考结果
- 如果某一阶段失败，先在该阶段目录中记录失败原因，再决定是否继续
- 不要在一次运行里混合多个阶段目标

当前阶段划分：

- Stage 01：轮辋轮心回转体创建
- Stage 02：轮心 PCD 孔创建
- Stage 03：轮心凹槽创建
- Stage 04：辐条生成

新线程的立即任务：

以 `prompts/01_revolve_body_prompt.md` 作为当前执行指令，先完成 Stage 01。

新线程结束时必须汇报：

- 修改了哪些文件
- 产出的模型路径
- 产出的记录文件路径
- 当前完成到了哪个阶段
- 下一阶段是否可以开始
