from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Tuple, Any
from enum import Enum
import json


class RimProfilePoint(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    radius: float = Field(description="该点到旋转轴的距离(mm)")
    height: float = Field(description="该点在轴向的位置(mm)")
    is_feature: bool = Field(default=False, description="是否为特征点(转角/凸起/凹陷)")
    feature_type: Optional[str] = Field(default=None, description="特征点类型: edge/lip/bump/valley")


class RimCrossSection(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    angle: float = Field(description="剖面角度(度)")
    profile_points: List[RimProfilePoint] = Field(default_factory=list, description="轮廓点序列")


class SpokeType(str, Enum):
    SOLID = "solid"
    HOLLOW = "hollow"
    SPOKE = "spoke"
    MULTI_SPOKE = "multi_spoke"


class HubFeatures(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    inner_diameter: float = Field(description="轮毂内孔直径(mm)")
    outer_diameter: float = Field(description="轮毂外径(mm)")
    height: float = Field(description="轮毂高度(mm)")
    bolt_hole_count: int = Field(default=0, description="螺栓孔数量")
    bolt_hole_diameter: float = Field(default=0.0, description="螺栓孔直径(mm)")
    bolt_hole_pcd: float = Field(default=0.0, description="螺栓孔节圆直径(mm)")
    center_hole_diameter: float = Field(default=0.0, description="中心孔直径(mm)")


class SpokeFeatures(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    count: int = Field(description="辐条数量")
    type: SpokeType = Field(description="辐条类型")
    width: float = Field(description="辐条宽度(mm)")
    thickness: float = Field(description="辐条厚度(mm)")
    pcd: float = Field(default=114.3, description="辐条节圆直径(mm)")
    angle_offset: float = Field(default=0.0, description="辐条角度偏移(度)")
    profile_points: List[Tuple[float, float]] = Field(default_factory=list, description="辐条轮廓点")


class RimFeatures(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    outer_diameter: float = Field(description="轮辋外径(mm)")
    inner_diameter: float = Field(description="轮辋内径(mm)")
    width: float = Field(description="轮辋宽度(mm)")
    lip_height: float = Field(default=0.0, description="轮缘高度(mm)")
    bead_seat_width: float = Field(default=0.0, description="胎圈座宽度(mm)")
    cross_sections: List[Any] = Field(default_factory=list, description="多个角度的径向剖面")
    main_profile: List[Any] = Field(default_factory=list, description="主轮廓点序列")


class WheelFeatures(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    overall_diameter: float = Field(description="整体直径(mm)")
    overall_width: float = Field(description="整体宽度(mm)")
    hub: HubFeatures = Field(description="轮毂特征")
    spokes: SpokeFeatures = Field(description="辐条特征")
    rim: RimFeatures = Field(description="轮辋特征")
    center_offset: float = Field(default=0.0, description="中心偏移量(mm)")
    fillet_radius: float = Field(default=3.0, description="倒角半径(mm)")
    rotation_axis: Tuple[float, float, float] = Field(default=(0, 0, 1), description="旋转轴方向")
    centroid: Tuple[float, float, float] = Field(default=(0, 0, 0), description="几何中心")
    
    def to_json(self, filepath: str) -> None:
        data = self.model_dump(mode='json')
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    @classmethod
    def from_json(cls, filepath: str) -> 'WheelFeatures':
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls(**data)
