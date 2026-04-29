import argparse
import os
import sys

from agents.coordinator import AgentCoordinator
from agents.perception_modeling_system import PerceptionModelingSystem
from console.user_console import UserConsole
from runtime.agent_runtime import AgentRuntime
from tools import StageExecutor


def main() -> None:
    parser = argparse.ArgumentParser(
        description="多智能体三维轮毂逆向建模系统 - STL 转 STEP"
    )
    parser.add_argument("stl_path", type=str, help="输入 STL 文件路径")
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="./output",
        help="输出目录 (默认: ./output)",
    )
    parser.add_argument(
        "-f",
        "--format",
        type=str,
        choices=["step", "stl"],
        default="step",
        help="输出格式 (默认: step)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["full", "perception-modeling", "runtime", "console", "stage"],
        default="full",
        help="运行模式: full、perception-modeling、runtime、console 或 stage (默认: full)",
    )
    parser.add_argument(
        "--stage",
        type=str,
        default="01",
        help="stage 模式下的阶段编号，可选: 01、02、03、04",
    )
    parser.add_argument(
        "--request",
        type=str,
        default="",
        help="用户控制台请求文本，仅在 console 模式下使用",
    )
    parser.add_argument("--log", action="store_true", help="保存智能体对话日志")
    parser.add_argument("--no-optimize", action="store_true", help="禁用迭代优化")
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="最大优化迭代次数 (默认: 3)",
    )
    parser.add_argument(
        "--target-score",
        type=float,
        default=80.0,
        help="目标评估分数 (默认: 80.0)",
    )
    parser.add_argument(
        "--enable-llm-agent",
        action="store_true",
        help="启用 LLM 规划层，规则仍保持为硬约束",
    )
    parser.add_argument(
        "--llm-model",
        type=str,
        default=None,
        help="LLM 规划层模型名称，默认读取环境变量或使用内置默认值",
    )

    args = parser.parse_args()

    if not os.path.exists(args.stl_path):
        print(f"错误: STL 文件不存在: {args.stl_path}")
        sys.exit(1)

    coordinator = None

    try:
        if args.mode == "perception-modeling":
            system = PerceptionModelingSystem(output_dir=args.output)
            results = system.run(stl_path=args.stl_path, output_format=args.format)
        elif args.mode == "console":
            console = UserConsole(
                output_dir=args.output,
                max_iterations=args.max_iterations,
                target_score=args.target_score,
                enable_llm_planning=args.enable_llm_agent,
                llm_model=args.llm_model,
            )
            request_text = args.request.strip() or (
                f"将 {args.stl_path} 转为 {args.format.upper()} 模型，"
                f"{'不要优化' if args.no_optimize else f'最多 {args.max_iterations} 轮优化'}。"
            )
            results = console.run_request(
                request=request_text,
                stl_path=args.stl_path,
                output_format=args.format,
                enable_optimization=not args.no_optimize,
            )
        elif args.mode == "runtime":
            runtime = AgentRuntime(
                output_dir=args.output,
                max_iterations=args.max_iterations,
                target_score=args.target_score,
                enable_llm_planning=args.enable_llm_agent,
                llm_model=args.llm_model,
            )
            results = runtime.run(
                stl_path=args.stl_path,
                output_format=args.format,
                enable_optimization=not args.no_optimize,
            )
        elif args.mode == "stage":
            executor = StageExecutor(output_dir=args.output)
            results = executor.run_stage(
                stl_path=args.stl_path,
                stage=args.stage,
                output_format=args.format,
            )
        else:
            coordinator = AgentCoordinator(
                output_dir=args.output,
                max_iterations=args.max_iterations,
                target_score=args.target_score,
            )
            results = coordinator.process_stl_to_step(
                stl_path=args.stl_path,
                output_format=args.format,
                enable_optimization=not args.no_optimize,
            )

        print("\n输出文件:")
        for key, path in results.items():
            print(f"  - {key}: {path}")

        if args.log and coordinator is not None:
            log_path = os.path.join(args.output, "agent_conversation.json")
            coordinator.save_conversation_log(log_path)
            print(f"\n智能体对话日志: {log_path}")

        if coordinator is not None:
            opt_summary = coordinator.get_optimization_summary()
            if opt_summary["total_iterations"] > 0:
                summary_path = os.path.join(args.output, "optimization_summary.json")
                import json

                with open(summary_path, "w", encoding="utf-8") as f:
                    json.dump(opt_summary, f, indent=2, ensure_ascii=False)
                print(f"\n优化摘要: {summary_path}")

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
