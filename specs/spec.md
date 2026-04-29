# 轮毂逆向建模系统优化规格说明

## 1. 项目背景

当前轮毂逆向建模系统存在以下核心问题：
1. **轮辋轮廓提取粗糙** - 仅使用简单尺寸参数，未获取精确边缘曲线
2. **辐条检测不准确** - 数量检测存在偏差，建模使用简单长方体
3. **轮毂造型简化** - 缺乏精密点数据，建模过程存在简化行为
4. **整体精度不足** - 豪斯多夫距离过大，未达到优秀标准

## 2. 优化目标

### 2.1 总体目标
- 豪斯多夫距离 < 5mm（优秀标准）
- 模型评估分数 ≥ 90分
- 所有特征尺寸误差 < 2%

### 2.2 具体目标

| 模块 | 当前问题 | 目标状态 |
|------|----------|----------|
| 轮辋感知 | 简单尺寸参数 | 精确边缘曲线（正交投影） |
| 辐条感知 | 数量检测偏差 | AI/视觉识别精确检测 |
| 辐条建模 | 简单长方体 | 曲面放样+圆周阵列 |
| 轮毂建模 | 简化造型 | 精密点数据驱动 |

## 3. 技术方案

### 3.1 轮辋轮廓精确提取

#### 3.1.1 正交投影法
```
输入: STL网格数据
处理流程:
1. 确定旋转轴方向
2. 生成正交投影平面（垂直于旋转轴）
3. 提取投影轮廓边缘点
4. 边缘点曲线拟合（B样条/贝塞尔曲线）
5. 轮廓分段识别（轮毂段、辐条段、轮辋段）

输出: 精确轮廓曲线数据
```

#### 3.1.2 数据结构
```python
class PreciseProfileCurve:
    curve_type: str  # "bspline" | "bezier" | "nurbs"
    control_points: List[Tuple[float, float, float]]
    knot_vector: List[float]
    degree: int
    segments: List[ProfileSegment]  # 分段信息
```

### 3.2 辐条智能检测

#### 3.2.1 水平投影法
```
输入: STL网格数据
处理流程:
1. 沿旋转轴方向切片
2. 生成水平投影图
3. 图像预处理（二值化、边缘检测）
4. 辐条区域分割
5. 数量统计 + 形状分析

输出: 辐条精确数量、位置、形状参数
```

#### 3.2.2 AI/视觉识别集成
```python
class SpokeDetector:
    def detect_by_projection(self, stl_path: str) -> SpokeDetectionResult:
        # 水平投影检测
        pass
    
    def detect_by_ai(self, projection_image: np.ndarray) -> SpokeDetectionResult:
        # AI模型检测（可选）
        pass
    
    def detect_by_contour(self, projection_image: np.ndarray) -> SpokeDetectionResult:
        # 轮廓分析检测
        pass
```

### 3.3 辐条曲面建模

#### 3.3.1 曲面放样法
```
输入: 辐条截面轮廓序列
处理流程:
1. 提取辐条起始截面（轮毂端）
2. 提取辐条终止截面（轮辋端）
3. 中间截面插值
4. 曲面放样生成
5. 圆周阵列复制

输出: 精确辐条曲面模型
```

#### 3.3.2 建模数据结构
```python
class SpokeLoftData:
    start_profile: List[Tuple[float, float]]  # 起始截面轮廓点
    end_profile: List[Tuple[float, float]]    # 终止截面轮廓点
    mid_profiles: List[List[Tuple[float, float]]]  # 中间截面
    loft_guides: List[Curve]  # 放样引导线
    twist_angle: float  # 扭转角度
```

### 3.4 轮毂精密建模

#### 3.4.1 数据驱动建模
```
原则: 从建模所需完整数据反推感知数据，不得简化

感知数据需求:
- 轮毂外表面点云
- 轮毂内腔点云
- 螺栓孔位置和尺寸
- 中心孔尺寸
- 过渡曲面数据

建模流程:
1. 点云数据精简（保持精度）
2. 曲面拟合
3. 实体生成
4. 特征添加（孔、倒角等）
```

#### 3.4.2 精度要求
| 特征 | 精度要求 |
|------|----------|
| 轮毂外径 | ±0.5mm |
| 轮毂高度 | ±0.5mm |
| 螺栓孔位置 | ±0.2mm |
| 螺栓孔直径 | ±0.1mm |
| 曲面偏差 | < 1mm |

## 4. 系统架构

### 4.1 模块结构
```
wheel_project/
├── agents/
│   ├── perception_agent.py      # 感知智能体（重构）
│   ├── modeling_agent.py        # 建模智能体（重构）
│   ├── evaluation_agent.py      # 评估智能体
│   └── coordinator.py           # 协调器
├── perception/
│   ├── projection_extractor.py  # 正交投影提取器
│   ├── profile_analyzer.py      # 轮廓分析器
│   ├── spoke_detector.py        # 辐条检测器
│   └── point_cloud_processor.py # 点云处理器
├── modeling/
│   ├── curve_fitter.py          # 曲线拟合器
│   ├── surface_lofter.py        # 曲面放样器
│   ├── pattern_generator.py     # 阵列生成器
│   └── precision_builder.py     # 精密建模器
├── models/
│   ├── wheel_features.py        # 特征数据模型（扩展）
│   ├── curve_data.py            # 曲线数据模型
│   └── surface_data.py          # 曲面数据模型
└── utils/
    ├── stl_utils.py             # STL工具
    ├── cad_utils.py             # CAD工具
    └── validation_utils.py      # 验证工具
```

### 4.2 数据流
```
STL输入
    ↓
[正交投影提取] → 轮廓曲线数据
    ↓
[水平投影分析] → 辐条检测数据
    ↓
[点云处理] → 精密点数据
    ↓
[曲线拟合] → 参数化曲线
    ↓
[曲面放样] → 辐条曲面
    ↓
[精密建模] → 完整轮毂模型
    ↓
[评估验证] → 质量报告
    ↓
STEP输出
```

## 5. 接口定义

### 5.1 感知智能体接口
```python
class EnhancedPerceptionAgent:
    def extract_orthogonal_projection(self, axis: np.ndarray) -> ProjectionResult:
        """提取正交投影轮廓"""
        pass
    
    def extract_horizontal_projection(self, height: float) -> ProjectionResult:
        """提取水平投影"""
        pass
    
    def detect_spokes_by_vision(self, projection: np.ndarray) -> SpokeDetectionResult:
        """视觉识别检测辐条"""
        pass
    
    def extract_precise_profile_curve(self) -> PreciseProfileCurve:
        """提取精确轮廓曲线"""
        pass
    
    def extract_hub_point_cloud(self) -> PointCloudData:
        """提取轮毂精密点云"""
        pass
```

### 5.2 建模智能体接口
```python
class PrecisionModelingAgent:
    def build_from_profile_curve(self, curve: PreciseProfileCurve) -> cq.Workplane:
        """从轮廓曲线构建模型"""
        pass
    
    def build_spoke_by_loft(self, loft_data: SpokeLoftData) -> cq.Workplane:
        """曲面放样构建辐条"""
        pass
    
    def circular_pattern_spokes(self, spoke: cq.Workplane, count: int) -> cq.Workplane:
        """圆周阵列辐条"""
        pass
    
    def build_hub_from_points(self, point_cloud: PointCloudData) -> cq.Workplane:
        """从点云构建轮毂"""
        pass
```

## 6. 验收标准

### 6.1 功能验收
- [ ] 正交投影轮廓提取正确
- [ ] 辐条数量检测准确率 > 95%
- [ ] 辐条曲面放样成功
- [ ] 轮毂精密建模完成

### 6.2 精度验收
- [ ] 豪斯多夫距离 < 5mm
- [ ] 尺寸误差 < 2%
- [ ] 曲面偏差 < 1mm
- [ ] 评估分数 ≥ 90

### 6.3 性能验收
- [ ] 完整流程执行时间 < 5分钟
- [ ] 内存占用 < 8GB
- [ ] 无崩溃和异常退出

## 7. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| AI模型不可用 | 辐条检测精度下降 | 保留传统算法作为备选 |
| 点云数据量大 | 处理速度慢 | 实现数据精简算法 |
| 曲面放样失败 | 辐条建模失败 | 提供多种放样策略 |
| 内存溢出 | 程序崩溃 | 分块处理大数据 |

## 8. 里程碑

| 阶段 | 内容 | 预期产出 |
|------|------|----------|
| M1 | 感知模块重构 | 精确轮廓+辐条检测 |
| M2 | 建模模块重构 | 曲面放样+精密建模 |
| M3 | 系统集成 | 完整流程打通 |
| M4 | 验收优化 | 达到优秀标准 |
