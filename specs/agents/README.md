# 智能体说明索引

## 1. 目录作用

该目录用于集中保存当前项目中各类智能体的角色说明文档。  
这些文档现在围绕干净主链组织：感知智能体提取当前方法需要的可信结构，建模智能体沿 accepted route 生成候选，视觉评估智能体负责多视角验收，优化逻辑只在明确归因后推动下一步。

## 2. 当前文档列表

- `coordinator_agent.md`  
  说明协调智能体如何组织阶段线程、约束阶段边界、控制阶段推进。

- `perception_agent.md`  
  说明感知智能体如何提取服务于干净主链的可信特征，并过滤 `actual_z` 等废案信号。

- `modeling_agent.md`  
  说明建模智能体如何沿 `tools/build_current_wheel_model.py` 固化的 accepted route 生成模型候选。

- `visual_evaluation_agent.md`
  说明视觉评估智能体如何围绕 T193 基准、多视角图像和 root/mid/tail 分区做验收。

- `evaluation_optimization_agent.md`  
  作为历史扩展说明，描述视觉评估后的受控修正推进方式。

## 3. 与其他资产的关系

当前项目中的智能体资产可以分成三层。

第一层是 skill 文档层，用来说明某类能力的方法和操作边界。  
第二层是 agent 说明文档层，也就是本目录中的各份 `agent.md` 文件，用来说明角色在干净主链中的职责边界和协同关系。  
第三层是 protocol 协议层，主要对应 `models/agent_protocol.py` 等统一对象定义文件，用来说明不同角色之间用什么数据结构完成衔接。

## 4. 使用方式

如果需要画系统框架图、整理论文第 2 章角色说明、或者继续补充新的线程型智能体资产，可以优先按下面顺序阅读：

1. `ACTIVE_MAINCHAIN_POLICY.md`
2. `CLEANUP_MINIMAL_README.md`
3. 本目录中的各份 `agent.md`
4. `skills/rewrite/*.md`
5. `models/agent_protocol.py`

这样可以先看清阶段链，再看清角色边界，最后再看协议对象。

## 5. 当前组织原则

本目录采用的组织原则是：

- 角色划分要和干净主链保持一致
- 每份文档都要说明职责、输入、输出、上下游和边界
- 不把旧主链的自动任务流或历史废案直接当成当前主叙述
- 角色说明要能直接服务论文写作、框架图绘制和后续资产扩展
