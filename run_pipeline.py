import subprocess
import sys
import os

class PipelineRunner:
    def __init__(self):
        self.python_exe = r'C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe'
    
    def run_command(self, script, desc):
        print(f"\n=== {desc} ===")
        result = subprocess.run([self.python_exe, script], 
                              capture_output=True, 
                              text=True, 
                              cwd=os.path.dirname(os.path.abspath(__file__)))
        
        if result.returncode == 0:
            print(f"✅ {desc} 成功")
            if result.stdout:
                print("输出:")
                print(result.stdout)
            return True
        else:
            print(f"❌ {desc} 失败")
            if result.stderr:
                print("错误:")
                print(result.stderr)
            return False
    
    def run_extraction(self):
        return self.run_command('test_extract.py', '特征提取')
    
    def run_modeling(self):
        return self.run_command('-c', '建模')
    
    def run_validation(self):
        return self.run_command('validate_model.py', '模型验证')
    
    def run_full_pipeline(self):
        print("🚀 开始完整建模流程")
        
        steps = [
            ('特征提取', self.run_extraction),
            ('建模', lambda: self.run_command('-c "from agents.modeling_agent import ModelingAgent; agent = ModelingAgent.from_json(\'output/wheel_features.json\'); model = agent.build_model(); agent.export_step(\'output/wheel_model.step\'); print(\'Model created\')"', '建模')),
            ('验证', self.run_validation)
        ]
        
        all_success = True
        for step_name, step_func in steps:
            if not step_func():
                all_success = False
                print(f"⚠️  {step_name} 失败，流程中断")
                break
        
        if all_success:
            print("\n🎉 完整流程执行成功！")
            print("模型文件: output/wheel_model.step")
        else:
            print("\n❌ 流程执行失败")

if __name__ == '__main__':
    runner = PipelineRunner()
    runner.run_full_pipeline()
