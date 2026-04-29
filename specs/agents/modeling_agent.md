# 建模智能体

## 角色定位

建模智能体负责把感知智能体提供的可信几何依据落实为 STEP/STL 模型。它不是旧流水线分支选择器，也不是从历史大文件中寻找“可能能用”的方案库。

当前建模智能体的核心职责是维护干净主链：沿用已接受的 T193 路线，在明确缺陷时做小范围、可解释的几何修正。

## 工作方法

建模智能体遵循当前 accepted route：

1. 从干净主入口启动建模。
2. 使用保留的 no-spoke base 和 feature JSON。
3. 用矩形基体构建辐条大体，确保 root 和 tail 连接范围足够长。
4. 用 section/refine 方法修辐条形状，而不是靠末端补丁拼接。
5. 在辐条添加后处理生产型轮心细节，包括 lug pocket、PCD hole、rear hub-face groove。
6. 用轮辋外轮廓曲线处理最终外侧边界，不使用简单圆柱外裁作为最终方案。
7. 导出 STEP、STL 和 metadata。
8. 交给视觉评估智能体验收。

建模智能体必须把方法控制在这条主链内。遇到问题时，优先修正这条主链的参数、顺序或局部模块，而不是恢复旧废案。

## 活跃入口

当前唯一公开建模入口是：

- `tools/build_current_wheel_model.py`

旧执行引擎只作为被该入口调用的实现细节。智能体不应直接运行旧执行脚本，也不应从旧执行脚本里挑历史开关组合。

## 输入

建模智能体通常接收：

- 感知特征
- 当前 accepted artifact
- 用户指出的几何缺陷
- 视觉评估结果
- 干净主链策略

输入的核心不是文件路径，而是明确的几何意图：要修 root、tail、中段凹槽、hub details，还是 rim boundary。

## 输出

建模智能体输出：

- STEP 模型
- STL 模型
- metadata
- 变更说明
- 已知剩余问题

如果没有视觉评估，必须说明模型只是候选，不是交付通过件。

## 几何判断规则

- root 或 tail 被平切，通常说明辐条基体/细修范围或 trim 顺序有问题。
- 外侧轻微穿模，优先检查最终 rim-curve boundary cleanup。
- 中段凹槽不正确，优先检查 section/refine 形状，不另建独立补丁。
- 沉孔、PCD、后侧凹槽缺失，优先检查 production hub cuts 的输入和调用时机。
- 整轮 heavy compound boolean 过慢或不稳定，不作为默认建模路线。

## 禁止复活的建模路线

以下路线默认归档：

- `actual_z` spoke lofting
- per-shape production cuts
- self-made post-spoke PCD cuts
- self-made counterbores
- synthetic front hub groove
- endpoint cap patch
- connector-fragment patch
- progressive fuse strategy
- cylinder outer-boundary final trim
- whole-wheel heavy compound boolean cut

建模智能体可以阅读旧文件理解历史，但不能把这些路线作为当前可选方案。

## 上下游关系

上游：

- 感知智能体
- 协调智能体
- 用户视觉反馈

下游：

- 视觉评估智能体
- 协调智能体

建模智能体负责生成候选，但是否通过由视觉评估智能体判断。

## 边界

建模智能体不负责：

- 重新定义感知特征
- 用废案绕开当前主链
- 只凭数值指标宣称通过
- 跳过视觉评估直接交付

它负责把当前方法做到稳定，而不是扩大方案空间。
