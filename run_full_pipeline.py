import sys
import os
import json
import traceback

os.chdir(r'c:\Users\Administrator\Downloads\wheel_project')
sys.path.insert(0, '.')

try:
    print("=" * 60)
    print("Step 1: Perception - Extract features from STL")
    print("=" * 60)
    from agents.perception_agent import PerceptionAgent
    agent = PerceptionAgent('input/wheel.stl')
    features = agent.extract_features()
    features.to_json('output/wheel_features.json')
    print(f"Overall Diameter: {features.overall_diameter:.2f} mm")
    print(f"Overall Width: {features.overall_width:.2f} mm")
    print(f"Width/Diameter Ratio: {features.overall_width / features.overall_diameter:.3f}")
    print(f"Rotation Axis: {features.rotation_axis}")
    
    print("\n" + "=" * 60)
    print("Step 2: Modeling - Create STEP model")
    print("=" * 60)
    from agents.modeling_agent import ModelingAgent
    modeler = ModelingAgent(features)
    modeler.build_model()
    modeler.export_step('output/wheel_model.step')
    print("Model saved to output/wheel_model.step")
    
    print("\n" + "=" * 60)
    print("Step 3: Evaluation - Calculate Hausdorff distance")
    print("=" * 60)
    from agents.evaluation_agent import EvaluationAgent
    evaluator = EvaluationAgent(
        stl_path='input/wheel.stl',
        step_path='output/wheel_model.step',
        features_path='output/wheel_features.json'
    )
    
    hausdorff_diffs = evaluator.evaluate_hausdorff()
    print("\nHausdorff evaluation results:")
    for diff in hausdorff_diffs:
        print(f"  - {diff.description}")
        print(f"    Expected: {diff.expected_value}, Actual: {diff.actual_value}")
        print(f"    Severity: {diff.severity}")
    
    result = evaluator.run_full_evaluation()
    print(f"\nOverall Score: {result.overall_score:.2f}")
    print(f"Is Acceptable: {result.is_acceptable}")
    print(f"Summary: {result.summary}")
    
    evaluator.export_report('output/evaluation_report.json')
    print("\nEvaluation report saved to output/evaluation_report.json")
    
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
