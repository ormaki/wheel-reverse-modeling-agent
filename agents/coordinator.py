import os
import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from agents.perception_agent import PerceptionAgent
from agents.modeling_agent import ModelingAgent, AdvancedModelingAgent
from agents.evaluation_agent import EvaluationAgent, EvaluationResult, DifferenceReport, Severity, DifferenceType
from models.wheel_features import WheelFeatures


class AgentState(str, Enum):
    IDLE = "idle"
    PERCEIVING = "perceiving"
    MODELING = "modeling"
    EVALUATING = "evaluating"
    OPTIMIZING = "optimizing"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class AgentMessage:
    sender: str
    receiver: str
    content: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class OptimizationStep:
    iteration: int
    evaluation_score: float
    issues_addressed: List[str]
    adjustments_made: Dict[str, Any]


class AgentCoordinator:
    def __init__(self, output_dir: str = "./output", max_iterations: int = 5, target_score: float = 80.0):
        self.state = AgentState.IDLE
        self.output_dir = output_dir
        self.max_iterations = max_iterations
        self.target_score = target_score
        
        self.perception_agent: Optional[PerceptionAgent] = None
        self.modeling_agent: Optional[ModelingAgent] = None
        self.evaluation_agent: Optional[EvaluationAgent] = None
        
        self.extracted_features: Optional[WheelFeatures] = None
        self.evaluation_result: Optional[EvaluationResult] = None
        
        self.messages: list = []
        self.optimization_history: List[OptimizationStep] = []
        self.current_iteration: int = 0
        
        self.perception_config: Dict[str, Any] = {}
        
        os.makedirs(output_dir, exist_ok=True)
    
    def _log_message(self, sender: str, receiver: str, content: Dict[str, Any]) -> None:
        message = AgentMessage(
            sender=sender,
            receiver=receiver,
            content=content
        )
        self.messages.append(message)
        print(f"[{message.timestamp}] {sender} -> {receiver}: {content.get('action', 'unknown')}")
    
    def initialize_perception_agent(self, stl_path: str, config: Optional[Dict] = None) -> None:
        if config:
            self.perception_config = config
        
        self._log_message(
            sender="Coordinator",
            receiver="PerceptionAgent",
            content={"action": "initialize", "stl_path": stl_path, "config": self.perception_config}
        )
        
        self.perception_agent = PerceptionAgent(stl_path, self.perception_config)
        self._log_message(
            sender="PerceptionAgent",
            receiver="Coordinator",
            content={"action": "initialized", "status": "success"}
        )
    
    def run_perception(self) -> WheelFeatures:
        if self.perception_agent is None:
            raise ValueError("Perception agent not initialized")
        
        self.state = AgentState.PERCEIVING
        self._log_message(
            sender="Coordinator",
            receiver="PerceptionAgent",
            content={"action": "extract_features"}
        )
        
        try:
            features_path = os.path.join(self.output_dir, "wheel_features.json")
            skill_result = self.perception_agent.run_perception_skill(output_path=features_path)
            self.extracted_features = skill_result.features
            
            self._log_message(
                sender="PerceptionAgent",
                receiver="Coordinator",
                content={
                    "action": "features_extracted",
                    "status": "success",
                    "features_path": features_path
                }
            )
            
            return self.extracted_features
            
        except Exception as e:
            self.state = AgentState.ERROR
            self._log_message(
                sender="PerceptionAgent",
                receiver="Coordinator",
                content={"action": "error", "message": str(e)}
            )
            raise
    
    def initialize_modeling_agent(self, features: Optional[WheelFeatures] = None) -> None:
        if features is None:
            features = self.extracted_features
        
        if features is None:
            raise ValueError("No features available for modeling agent")
        
        self._log_message(
            sender="Coordinator",
            receiver="ModelingAgent",
            content={"action": "initialize", "features": features.model_dump()}
        )
        
        self.modeling_agent = AdvancedModelingAgent(features)
        
        self._log_message(
            sender="ModelingAgent",
            receiver="Coordinator",
            content={"action": "initialized", "status": "success"}
        )
    
    def run_modeling(self, output_format: str = "step") -> str:
        if self.modeling_agent is None:
            raise ValueError("Modeling agent not initialized")
        
        self.state = AgentState.MODELING
        self._log_message(
            sender="Coordinator",
            receiver="ModelingAgent",
            content={"action": "build_model", "format": output_format}
        )
        
        try:
            if output_format.lower() == "step":
                output_path = os.path.join(self.output_dir, "wheel_model.step")
            else:
                output_path = os.path.join(self.output_dir, "wheel_model.stl")

            self.modeling_agent.run_modeling_skill(
                output_format=output_format,
                output_path=output_path,
            )
            
            self._log_message(
                sender="ModelingAgent",
                receiver="Coordinator",
                content={
                    "action": "model_completed",
                    "status": "success",
                    "output_path": output_path
                }
            )
            
            return output_path
            
        except Exception as e:
            self.state = AgentState.ERROR
            self._log_message(
                sender="ModelingAgent",
                receiver="Coordinator",
                content={"action": "error", "message": str(e)}
            )
            raise
    
    def initialize_evaluation_agent(self, stl_path: str, step_path: str, features_path: str) -> None:
        self._log_message(
            sender="Coordinator",
            receiver="EvaluationAgent",
            content={"action": "initialize", "stl_path": stl_path, "step_path": step_path}
        )
        
        self.evaluation_agent = EvaluationAgent(
            stl_path=stl_path,
            step_path=step_path,
            features_path=features_path
        )
        
        self._log_message(
            sender="EvaluationAgent",
            receiver="Coordinator",
            content={"action": "initialized", "status": "success"}
        )
    
    def run_evaluation(self) -> EvaluationResult:
        if self.evaluation_agent is None:
            raise ValueError("Evaluation agent not initialized")
        
        self.state = AgentState.EVALUATING
        self._log_message(
            sender="Coordinator",
            receiver="EvaluationAgent",
            content={"action": "evaluate"}
        )
        
        try:
            self.evaluation_result = self.evaluation_agent.run_full_evaluation()
            
            report_path = os.path.join(self.output_dir, "evaluation_report.json")
            self.evaluation_agent.export_report(report_path)
            
            viz_path = os.path.join(self.output_dir, "evaluation_comparison.png")
            self.evaluation_agent.visualize_comparison(viz_path)
            
            self._log_message(
                sender="EvaluationAgent",
                receiver="Coordinator",
                content={
                    "action": "evaluation_completed",
                    "status": "success",
                    "score": self.evaluation_result.overall_score,
                    "is_acceptable": self.evaluation_result.is_acceptable,
                    "report_path": report_path
                }
            )
            
            return self.evaluation_result
            
        except Exception as e:
            self.state = AgentState.ERROR
            self._log_message(
                sender="EvaluationAgent",
                receiver="Coordinator",
                content={"action": "error", "message": str(e)}
            )
            raise
    
    def analyze_issues(self) -> Dict[str, List[Dict]]:
        if not self.evaluation_result:
            return {"perception": [], "modeling": []}
        
        perception_issues = []
        modeling_issues = []
        
        for diff in self.evaluation_result.differences:
            issue = {
                "type": diff.difference_type.value,
                "severity": diff.severity.value,
                "component": diff.component,
                "description": diff.description,
                "deviation": diff.deviation_percent,
                "suggestion": diff.suggestion
            }
            
            if diff.difference_type in [DifferenceType.DIMENSION_MISMATCH, DifferenceType.PROFILE_ERROR, DifferenceType.FEATURE_MISSING]:
                perception_issues.append(issue)
            elif diff.difference_type in [DifferenceType.SHAPE_DEVIATION, DifferenceType.SYMMETRY_ISSUE, DifferenceType.SURFACE_QUALITY]:
                modeling_issues.append(issue)
        
        return {"perception": perception_issues, "modeling": modeling_issues}
    
    def generate_perception_adjustments(self, issues: List[Dict]) -> Dict[str, Any]:
        adjustments = {}
        
        for issue in issues:
            component = issue.get("component", "")
            deviation = issue.get("deviation", 0)
            
            if "尺寸" in component or "dimension" in component.lower():
                adjustments["num_slices"] = min(self.perception_config.get("num_slices", 2000) * 2, 10000)
                adjustments["radius_threshold"] = max(self.perception_config.get("radius_threshold", 0.8) * 0.9, 0.5)
            
            if "轮廓" in component or "profile" in component.lower():
                adjustments["num_slices"] = min(self.perception_config.get("num_slices", 2000) * 2, 10000)
                adjustments["feature_threshold"] = max(self.perception_config.get("feature_threshold", 0.5) * 0.7, 0.1)
            
            if "辐条" in component or "spoke" in component.lower():
                adjustments["spoke_detection_sensitivity"] = 1.2
            
            if "轮毂" in component or "hub" in component.lower():
                adjustments["hub_detection_method"] = "percentile"
        
        return adjustments
    
    def apply_perception_adjustments(self, adjustments: Dict[str, Any]) -> None:
        if not adjustments:
            return
        
        print(f"\n[Coordinator] 应用感知参数调整: {adjustments}")
        
        self.perception_config.update(adjustments)
        
        if self.perception_agent:
            for key, value in adjustments.items():
                if hasattr(self.perception_agent, key):
                    setattr(self.perception_agent, key, value)
    
    def run_optimization_iteration(self, stl_path: str) -> OptimizationStep:
        self.current_iteration += 1
        self.state = AgentState.OPTIMIZING
        
        print(f"\n{'='*60}")
        print(f"[Coordinator] 优化迭代 #{self.current_iteration}")
        print(f"{'='*60}")
        
        self._log_message(
            sender="Coordinator",
            receiver="All",
            content={"action": "optimization_iteration", "iteration": self.current_iteration}
        )
        
        issues_addressed = []
        adjustments_made = {}
        
        issues = self.analyze_issues()
        
        perception_adjustments = self.generate_perception_adjustments(issues["perception"])
        if perception_adjustments:
            self.apply_perception_adjustments(perception_adjustments)
            adjustments_made["perception"] = perception_adjustments
            issues_addressed.extend([i["component"] for i in issues["perception"][:3]])
            
            print("\n[Coordinator] 重新提取特征...")
            features_path = os.path.join(self.output_dir, f"wheel_features_iter{self.current_iteration}.json")
            skill_result = self.perception_agent.run_perception_skill(output_path=features_path)
            self.extracted_features = skill_result.features
        
        print("\n[Coordinator] 重新构建模型...")
        self.modeling_agent = AdvancedModelingAgent(self.extracted_features)
        step_path = os.path.join(self.output_dir, f"wheel_model_iter{self.current_iteration}.step")
        self.modeling_agent.run_modeling_skill(output_format="step", output_path=step_path)
        
        features_path = os.path.join(self.output_dir, "wheel_features.json")
        self.initialize_evaluation_agent(stl_path, step_path, features_path)
        self.evaluation_result = self.run_evaluation()
        
        score = self.evaluation_result.overall_score if self.evaluation_result else 0
        
        step = OptimizationStep(
            iteration=self.current_iteration,
            evaluation_score=score,
            issues_addressed=issues_addressed,
            adjustments_made=adjustments_made
        )
        
        self.optimization_history.append(step)
        
        return step
    
    def process_stl_to_step(self, stl_path: str, output_format: str = "step", enable_optimization: bool = True) -> Dict[str, str]:
        results = {}
        
        print("=" * 60)
        print("多智能体轮毂逆向建模系统启动")
        print("=" * 60)
        
        print("\n[阶段1] 初始化感知智能体...")
        self.initialize_perception_agent(stl_path)
        
        print("\n[阶段2] 执行特征提取...")
        features = self.run_perception()
        results["features_json"] = os.path.join(self.output_dir, "wheel_features.json")
        
        self._print_features_summary(features)
        
        print("\n[阶段3] 初始化建模智能体...")
        self.initialize_modeling_agent(features)
        
        print("\n[阶段4] 执行参数化建模...")
        output_path = self.run_modeling(output_format)
        results["output_model"] = output_path
        
        print("\n[阶段5] 初始化评估智能体...")
        features_path = os.path.join(self.output_dir, "wheel_features.json")
        self.initialize_evaluation_agent(stl_path, output_path, features_path)
        
        print("\n[阶段6] 执行模型评估...")
        eval_result = self.run_evaluation()
        results["evaluation_report"] = os.path.join(self.output_dir, "evaluation_report.json")
        results["evaluation_visualization"] = os.path.join(self.output_dir, "evaluation_comparison.png")
        
        if enable_optimization and (not eval_result.is_acceptable or eval_result.overall_score < self.target_score):
            print(f"\n[阶段7] 开始迭代优化 (目标分数: {self.target_score})...")
            
            while (self.current_iteration < self.max_iterations and 
                   eval_result.overall_score < self.target_score):
                
                step = self.run_optimization_iteration(stl_path)
                
                print(f"\n迭代 #{step.iteration} 完成:")
                print(f"  - 评估分数: {step.evaluation_score:.1f}")
                print(f"  - 处理的问题: {', '.join(step.issues_addressed[:3]) if step.issues_addressed else '无'}")
                
                if step.evaluation_score >= self.target_score:
                    print(f"\n[OK] 达到目标分数 {self.target_score}!")
                    break
                
                eval_result = self.evaluation_result
            
            if self.current_iteration >= self.max_iterations:
                print(f"\n[WARN] 达到最大迭代次数 {self.max_iterations}")
        
        self.state = AgentState.COMPLETED
        
        print("\n" + "=" * 60)
        print("建模完成!")
        print("=" * 60)
        
        self._print_final_summary()
        
        return results
    
    def _print_features_summary(self, features: WheelFeatures) -> None:
        print(f"\n提取的特征参数:")
        print(f"  - 整体直径: {features.overall_diameter:.2f} mm")
        print(f"  - 整体宽度: {features.overall_width:.2f} mm")
        print(f"  - 轮毂外径: {features.hub.outer_diameter:.2f} mm")
        print(f"  - 轮毂高度: {features.hub.height:.2f} mm")
        print(f"  - 辐条数量: {features.spokes.count}")
        print(f"  - 辐条类型: {features.spokes.type.value}")
        print(f"  - 轮辋外径: {features.rim.outer_diameter:.2f} mm")
        print(f"  - 轮辋宽度: {features.rim.width:.2f} mm")
    
    def _print_final_summary(self) -> None:
        print(f"\n最终评估分数: {self.evaluation_result.overall_score:.1f}/100")
        print(f"模型质量: {'可接受' if self.evaluation_result.is_acceptable else '需要改进'}")
        
        if self.optimization_history:
            print(f"\n优化历史:")
            for step in self.optimization_history:
                print(f"  迭代 #{step.iteration}: 分数 {step.evaluation_score:.1f}")
        
        print(f"\n输出文件:")
        print(f"  - 特征文件: {os.path.join(self.output_dir, 'wheel_features.json')}")
        print(f"  - 模型文件: {os.path.join(self.output_dir, 'wheel_model.step')}")
        print(f"  - 评估报告: {os.path.join(self.output_dir, 'evaluation_report.json')}")
        print(f"  - 对比可视化: {os.path.join(self.output_dir, 'evaluation_comparison.png')}")
    
    def get_conversation_log(self) -> list:
        return [
            {
                "timestamp": msg.timestamp,
                "from": msg.sender,
                "to": msg.receiver,
                "content": msg.content
            }
            for msg in self.messages
        ]
    
    def save_conversation_log(self, filepath: str) -> None:
        log = self.get_conversation_log()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(log, f, indent=2, ensure_ascii=False)
    
    def get_optimization_summary(self) -> Dict[str, Any]:
        return {
            "total_iterations": self.current_iteration,
            "final_score": self.evaluation_result.overall_score if self.evaluation_result else 0,
            "is_acceptable": self.evaluation_result.is_acceptable if self.evaluation_result else False,
            "history": [
                {
                    "iteration": step.iteration,
                    "score": step.evaluation_score,
                    "issues": step.issues_addressed,
                    "adjustments": step.adjustments_made
                }
                for step in self.optimization_history
            ]
        }
