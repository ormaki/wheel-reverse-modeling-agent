---
name: perception-skill
description: 从 STL 网格中提取轮毂几何特征，并为下游参数化建模准备结构化输入。
---

# 感知能力说明

## 功能概述

该能力用于驱动轮毂逆向建模流程中“STL 到结构化特征”的感知阶段。工程实现以 Python 感知逻辑为准，这份说明文件的作用是明确如何调用该能力，以及哪些工程文件与输出结果和它直接相关。

## 项目文件

在修改感知行为之前，应优先阅读以下文件：

- `D:\桌面\wheel_project-1b6e756c9770\main.py`
- `D:\桌面\wheel_project-1b6e756c9770\agents\perception_agent.py`
- `D:\桌面\wheel_project-1b6e756c9770\skills\perception_skill.py`
- `D:\桌面\wheel_project-1b6e756c9770\models\wheel_features.py`

当请求只涉及“双智能体协同路径”时，还应补充阅读：

- `D:\桌面\wheel_project-1b6e756c9770\agents\perception_modeling_system.py`

## 主要工作流

1. 确认 STL 输入路径存在。
2. 优先复用现有的 `PerceptionAgent` 实现，而不是另起一套特征提取逻辑。
3. 当用户需要结构化特征结果或 `wheel_features.json` 文件时，调用 `run_perception_skill()`。
4. 若用户没有指定其他位置，就将 JSON 结果写入项目的 `output/` 目录。
5. 汇报对后续建模最关键的提取结果，例如整体直径、宽度、轮心尺寸、辐条数量或类型、轮辋尺寸以及输出路径。

## 工程提示词摘录

当前工程中，感知能力并不是脱离上下文独立工作的，它还会受到阶段提示词的直接约束。和感知最相关的提示要求可以概括为：

- `prompts/01_revolve_body_prompt.md`：感知应优先识别轮辋和轮心的主回转轮廓，保证整体比例、直径、宽度和轮心主体关系合理，不提前混入 PCD 孔、轮心凹槽和辐条判断。
- `prompts/02_pcd_holes_prompt.md`：感知应围绕稳定回转体基体确认 PCD 孔数量、分布圆和孔位关系，不重写 Stage 01 的主回转体逻辑。
- `prompts/03_hub_grooves_prompt.md`：感知应识别轮心凹槽的主要参数与分布，并保持凹槽与轮心主体、PCD 孔之间的真实关系，不把辐条连接问题带入这一阶段。
- `prompts/04_spokes_prompt.md`：感知应聚焦辐条的宽度、厚度、根部与尾部连接关系，在失败时明确区分截面问题、连接问题和阵列问题，而不是把前面阶段的问题伪装成辐条问题。

这些提示词共同决定了感知阶段“当前该看什么、不能看什么、结果要服务哪个阶段”的具体工作方式。

## 调用方式

当只需要执行感知阶段时，可直接按下面方式调用：

```python
from agents.perception_agent import PerceptionAgent

agent = PerceptionAgent(stl_path=r"D:\桌面\wheel_project-1b6e756c9770\input\wheel.stl")
result = agent.run_perception_skill(
    output_path=r"D:\桌面\wheel_project-1b6e756c9770\output\wheel_features.json"
)

features = result.features
print(features.overall_diameter, features.spokes.count)
```

如果请求是以“运行整个项目流程”的形式提出，也可以通过命令行入口执行：

```powershell
python D:\桌面\wheel_project-1b6e756c9770\main.py `
  D:\桌面\wheel_project-1b6e756c9770\input\wheel.stl `
  --mode perception-modeling `
  -o D:\桌面\wheel_project-1b6e756c9770\output `
  -f step
```

## 运行规则

- 不要用纯文字推理替代真正的感知逻辑。
- 不要绕开 `models\wheel_features.py`，要保证输出与 `WheelFeatures` 兼容。
- 如果必须改行为，优先只在 `PerceptionAgent` 和 `skills\perception_skill.py` 周边做小改动。
- 如果用户要求提升提取精度，先检查 `PerceptionAgent` 的阈值和切片逻辑。
- 如果用户需要端到端几何输出，应把特征结果交给建模阶段，而不是在这里混入建模步骤。

## 预期输出

默认产物：

- `D:\桌面\wheel_project-1b6e756c9770\output\wheel_features.json`

预期内容：

- 整体直径与宽度
- 轮心、辐条和轮辋特征分组
- 旋转轴与质心
- 建模所需的轮廓与截面数据
