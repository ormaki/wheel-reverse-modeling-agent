# Pipeline Active Handoff

## 2026-04-24 主流水线3继续推进记录

- 已继续验证 T7 之后的分支；当前最佳仍保持 `output/extrudeLoopT7_P1_m3radP1_m5radP2.step`，不要被后续 T21-T26 覆盖。
- 额外固定视觉评估了 `output/extrudeLoopT17_T7_m9SectionRoot35.step`。结论：B9 专用模板能让 member9 局部指标改善（member9 `score=0.719, unmatched=0.006`，优于 T7 的 `score=0.806, unmatched=0.013`），但会让整体 `spoke_overlap` 降到 `0.3693`，不适合作为全局新基线。
- 新排除分支：
  - `output/extrudeLoopT23_T7_m9Upper02.step`：只给 member9 用小幅 upper lift，`spoke_overlap=0.3565`，退化。
  - `output/extrudeLoopT24_T7_m9B9angM15.step`：B9 member9 角度 -1.5 度，`spoke_overlap=0.3570`，退化。
  - `output/extrudeLoopT25_T7_m9B9angP15.step`：B9 member9 角度 +1.5 度，`spoke_overlap=0.3645`，退化。
  - `output/extrudeLoopT26_T7_m5Upper02.step`：只给 member5 用小幅 upper lift，`spoke_overlap=0.3734`，退化。
- 截面只读诊断显示 member7/member9 的 mesh-derived section upper 本身贴近 guide；问题不是简单“抽取上缘太低”，而是模板跨成员复用后在固定评估/投影对齐中产生局部视觉缺陷。下一步不要继续做 upper lift、planform width-only、B9 angle sweep；应转向更稳定的局部成员评估/装配策略，例如导出成员级 STL 后用同一固定对齐诊断单成员差异，避免全局自动对齐掩盖真实局部变化。

## 2026-04-24 成员级诊断补充

- 已为 T7 与 T17 重新装配并导出成员级 STL：
  - `output/member_diag_T7_members/_member_diag_{i}.stl`
  - `output/member_diag_T17_members/_member_diag_{i}.stl`
- 成员级 overlap 诊断输出：
  - `output/member_diag_T7_members/member_overlap_T7.json`
  - `output/member_diag_T17_members/member_overlap_T17.json`
- 结论：T17 相比 T7 只有 member9 真实改善，member9 `overlap 0.5701 -> 0.5836`、`nn_fwd 3.802 -> 3.124`、`nn_bwd 3.167 -> 2.832`；member3/5/7 成员级结果不变。此前固定视觉评估中 m3/m5 变差，主要来自全局自动对齐/投影诊断的连带扰动，不是这些成员几何真的改变。
- 但把 T17 强制套用 T7 对齐参数后仍明显差于 T7，`output/fixed_align_T7_vs_T17_metrics.json` 显示 `T17_forcedT7 spoke=0.3419`；因此 B9 member9 虽局部好，仍不能作为全局候选。
- 已批量扫描 member5 已有模板，输出在 `output/member5_template_scan/`。局部最好的是 `templB5_legacyRoot55`，其次是 `templB5_sectionRoot45_radP2`，但完整装配都退化：
  - `output/extrudeLoopT27_T7_m5B5Legacy55.step`：`spoke_overlap=0.3533`
  - `output/extrudeLoopT28_T7_m5B5SectionRoot45.step`：`spoke_overlap=0.3784`
- T28 的固定视觉成员诊断也确认不是可接受替换：member5 `visual_error_score=0.914`，差于 T7 的 `0.896`，且 member7/member2 明显变差。
- 现在明确排除：直接换 B5 模板修 member5、B9 专用修 member9、B9 小角度扫描、upper lift、planform width-only。下一步应做“成员级闭环生成”：先以 `diagnose_template_member_radial_error.py` / `diagnose_member_spoke_overlap.py` 为局部评分，再生成只针对单成员的截面修正模板，只有局部与固定视觉同时改善时才进入完整装配。

## 2026-04-24 接手主流水线3追加记录

- 已定位 Codex 线程 `019d7ff6-27a2-7722-b293-ef403e67a200`，线程名为“主流水线3”。最后有效结论：当前最佳候选仍是 `output/extrudeLoopT7_P1_m3radP1_m5radP2.step`，指标为 `front=0.6547, side=0.7428, spoke=0.4043, nn_fwd=3.241, nn_bwd=3.357`。
- T7 的固定视觉评估位置：`output/eval_stage_extrudeLoopT7_P1_m3radP1_m5radP2/visual_diag_extrudeLoopT7_P1_m3radP1_m5radP2/`。`visual_worst_member_profiles.png` 显示主要缺陷不是整体径向位置，而是 member5/7/9 中段 STEP upper 低于 STL upper；member9 宽度差最大，`width_delta=-2.85mm`。
- 本次新增了非默认参数到 `tools/run_spoke_extrude_refine_array_model.py`：`--refine-planform-width-only`、`--refine-planform-expand-only`、`--refine-planform-min-expand-mm`。默认行为不变，目的是测试“只按 planform 扩宽截面、不移动截面中心”。
- 已排除的新实验：`output/extrudeLoopT21_T7_widthOnly018.step` 全 slot1 使用 width-only planform 模板，`spoke_overlap=0.3792`；`output/extrudeLoopT22_T7_m9WidthOnly018.step` 只用于 member9，`spoke_overlap=0.3648`。二者都低于 T7。
- 因此不要继续沿“planform 投影扩宽”路线扫强度；它会破坏整体 spoke 对齐。下一步更应针对截面抽取/上缘选择本身：用 member5/7/9 的剖面图驱动上缘候选选择或局部上缘重建，而不是做投影缩放、全局 planform match 或成员后处理缩放。

更新时间：2026-04-12
范围：仅接替 `.codex` 中的 `流水线` 线程，不包含 `流水线2`、论文线、`fuxian` 分支。

## 1. 线程来源

- Codex 会话索引中的 `流水线` 线程对应会话 id：
  `019d1907-9600-7470-b02c-a76b2711caf0`
- 该线程的显式交接文档是：
  `D:\桌面\wheel_project-1b6e756c9770\HANDOFF_20260323.md`
- 较早的稳定基线补充说明在：
  `D:\桌面\wheel_project-1b6e756c9770\HANDOFF_20260317.md`

结论：当前应以 `HANDOFF_20260323.md` 为主，`HANDOFF_20260317.md` 仅作为更早期稳定路径参考。

## 2. 当前主线目标

当前主线不是再修旧的减法开窗路径，而是继续推进：

- 保持基体是合理的单实体回转体
- 保持后脸凹槽由真实感知结果驱动
- 使用 `hybrid region + additive spoke members` 重建辐条
- 避免回到局部截面整圈回转、多实体、碎片体方案

用户当前最关心的是：

- 辐条中段可见宽度是否贴近原件
- 辐条根部、尾部和 Z 向厚度是否真实
- 每次判断都能回到日志、预览图和模型上自证

## 3. 双基线产物

### 3.1 后脸凹槽正确、辐条尚未大改的回退锚点

- `output\wheel_20260318_rear_true_aligned_v2.step`
- `output\wheel_20260318_rear_true_aligned_v2.log`
- `output\wheel_20260318_rear_true_aligned_v2_perception.png`
- `output\wheel_20260318_rear_true_aligned_v2_hub_grooves.png`

### 3.2 当前 `流水线` 线程主尝试

- `output\wheel_20260322_hybrid_region_v2.step`
- `output\wheel_20260322_hybrid_region_v2.log`
- `output\wheel_20260322_hybrid_region_v2_perception.png`
- `output\wheel_20260322_hybrid_region_v2_spokeless.png`
- `output\wheel_20260322_hybrid_region_v2_hub_grooves.png`

`wheel_20260322_hybrid_region_v2.log` 的关键状态：

- `Spokeless hybrid section body generated from full guarded section + local spoke-free replacement`
- `Hub rear-face grooves cut: 5 (Z=39.86 -> 57.86, effective Z=39.9 -> 57.94, no-op=0)`
- `Spokeless additive spoke members prepared: type=paired_spoke, members=10, merged=9, solids=1`
- `motif_2_member_5` 在加法辐条阶段被丢弃

结论：后脸凹槽已接稳，但加法辐条只完成了 `9/10`，且整体辐条逻辑仍未收敛。

## 4. 已确认成立的判断

1. 后脸凹槽应来自原件后脸切片，不是前脸，不是 synthetic fallback。
2. `spokeless` 专项图中的蓝色闭合岛不能直接整圈回转成基体。
3. 基体应走 `full guarded section + local spoke-free replacement -> hybrid region`。
4. 辐条可见形状不能继续由减法窗孔主导，必须转向正向加法实体。
5. 当前造型更接近 `5 对 motif`，而不是 `10` 根完全独立单辐条。

## 5. 当前最可能的错误源

按 `HANDOFF_20260323.md` 的结论，优先怀疑以下三项：

1. 基体与辐条职责仍然混叠，导致基体没有真正“去辐条化”。
2. 成员真实截面对象取错，拿到了 region/band/keepout 裁切后的剩余几何，而不是左右成员真实截面。
3. `9/10 -> 10/10` 不是全部问题；即使全部并入，如果截面对象仍错，辐条宽度和厚度仍会错。

## 6. 现代码中的关键入口

以下行号以当前 `stl_to_step_pipeline.py` 为准：

- `build_member_actual_slice_guide(...)`：3124
- `extract_member_actual_z_profile_stack(...)`：4050
- `derive_spoke_motif_section_groups(...)`：5231
- `extract_hub_bottom_groove_regions(...)`：5654
- `build_spokeless_spoke_members(...)`：13109
- `build_motif_member_spoke(...)`：14528
- `strict additive / spokeless member merge` 主逻辑：15610 附近

当前代码含义：

- 3124/4050 一带负责从感知截面生成成员引导区与 `actual z` 轮廓栈。
- 13109/14528 一带负责把单个 motif member 转成实际 CadQuery 实体。
- 15610 之后负责把 member 并入 `hub_body` / `rim`，统计 `merged`、`staged`、`solids`。

## 7. 接手后的任务顺序

严格按这个顺序，不并行大改：

1. 先守住双基线，不回退后脸凹槽，也不破坏 `hybrid region`。
2. 不再尝试整圈回转 `spokeless` 闭合岛。
3. 先排查成员截面对象定义，而不是继续优先调减法窗孔或全局切片方向。
4. 先把加法辐条从 `9/10` 推到 `10/10`。
5. 在 `10/10` 基础上，优先修中段可见宽度。
6. 根部/尾部大型 patch 暂缓，除非中段已经稳定。

## 8. 验证标准

优先看这几个指标：

- `covered_member_count` 或同义统计是否达到 `10/10`
- 最终 `solid_count` 是否仍为 `1`
- 后脸凹槽是否仍保持有效切入
- 辐条中段宽度是否明显更接近原件

常用命令：

```powershell
python -X utf8 stl_to_step_pipeline.py input/wheel.stl
python -X utf8 stl_to_step_pipeline.py input/wheel.stl --preview-only
```

## 9. 明确不要做的事

- 不要接入 `流水线2` 的任务目标。
- 不要回到 full-body unified revolve 主路。
- 不要再把减法窗孔 keepout 当作辐条正形主解法。
- 不要为局部视觉改进牺牲单实体导出。
- 不要在没有证据的情况下硬编码到 `10` 根辐条。

## 10. 当前一句话总结

`流水线` 线程当前要接手的不是“继续找新基体”，而是守住 `hybrid region + rear grooves` 这条已经成立的主路，围绕 `build_member_actual_slice_guide -> extract_member_actual_z_profile_stack -> build_motif_member_spoke -> additive merge` 这条链路，把加法辐条从 `9/10` 推到 `10/10`，并先把中段宽度做对。

## 2026-04-24 mainline-3 continuation notes

Active baseline remains:

- `output/extrudeLoopT7_P1_m3radP1_m5radP2.step`
- `front_overlap=0.6547`, `side_overlap=0.7428`, `spoke_overlap=0.4043`
- `nn_mean_fwd_mm=3.2410`, `nn_mean_bwd_mm=3.3574`

Validated after takeover:

- Added visual diagnostics for T7 at `output/eval_stage_extrudeLoopT7_P1_m3radP1_m5radP2_vizonly/`.
- T7 worst visual members: member5 score 0.896, member7 score 0.833, member9 score 0.806, member8 score 0.802, member2 score 0.796.
- T7 member5 still has center/upper mismatch; member7/member9 still show missing mid material, but earlier width/template replacements regress global metrics.

Completed local perturbation branches that did not beat T7:

- T29 `output/extrudeLoopT29_T7_m5AngM075.step`: spoke 0.3597.
- T30 `output/extrudeLoopT30_T7_m5AngP075.step`: spoke 0.3852.
- T31 `output/extrudeLoopT31_T7_m5AngM15.step`: spoke 0.3906.
- T32 `output/extrudeLoopT32_T7_m5AngP15.step`: spoke 0.3704.
- T33 `output/extrudeLoopT33_T7_m7AngM075.step`: spoke 0.3730.
- T34 `output/extrudeLoopT34_T7_m7AngP075.step`: spoke 0.3625.
- T35 `output/extrudeLoopT35_T7_m7AngM15.step`: spoke 0.3998.
- T36 `output/extrudeLoopT36_T7_m7AngP15.step`: spoke 0.3968.

T35 was the closest member7 angle branch, but visual diagnostics at `output/eval_stage_extrudeLoopT35_T7_m7AngM15_vizonly/` show member5 error worsened to 1.146 and member7 remained worse than T7. Conclusion: do not continue angle-only perturbations for member5 or member7 unless paired with a new geometry source.

Recommended next move:

- Keep T7 as the baseline.
- Stop repeating member5/member7 angle, upper-lift, width-only, and B5/B9 direct replacement tests.
- Next useful branch should change the geometry extraction/source for slot1 mid material in a controlled way, then gate with `tools/run_visual_evaluation_stage.py` using seed 42.

Additional branch after the notes above:

- T37 `output/extrudeLoopT37_T7_m7WidthOnly018.step`: member7 only replaced with `templB7_root55_widthOnly018.step`; metrics `front=0.6519`, `side=0.7417`, `spoke=0.3520`, `nn_fwd=3.2428`, `nn_bwd=3.3712`.
- Conclusion: member7 width-only using the root55-derived template is a hard regression. The likely issue is the geometry source/root replacement, not just tangent width. Do not reuse `templB7_root55_widthOnly018.step` for member7.

## 2026-04-24 radial-band hybrid branch

Added tool:

- `tools/hybridize_spoke_template_radial_band.py`
- Purpose: replace only one radial band of a spoke template with a donor template while preserving the base template outside that band.
- Supports `--base-rotate-deg` and `--band-rotate-deg` so donor/base templates can be aligned before hybridization.

Completed candidates, all below T7:

- T38 `output/extrudeLoopT38_T7_m7MidWidthOnly018.step`: member7 only, base `templLoopB7_intersect`, donor `templB7_root55_widthOnly018`, band 95-158, spoke 0.3735, side 0.7208.
- T39 `output/extrudeLoopT39_T7_m7MidRootInt55.step`: member7 only, base `templLoopB7_intersect`, donor `templLoopB7_rootIntReplace55`, band 95-158, spoke 0.3636.
- T40 `output/extrudeLoopT40_T7_m7MidRootInt55Narrow.step`: member7 only, same donor as T39, narrower band 110-145, spoke 0.3781.
- T41 `output/extrudeLoopT41_T7_m9MidB9Narrow.step`: member9 only, base `templLoopB7_rootIntReplace55` rotated -287.996 deg to member9, donor `templB9_sectionSpanRoot35_nogap`, band 110-145, spoke 0.3646.

Interpretation:

- Mid-band donor replacement did not convert the member-level B9/width observations into a full-wheel gain.
- Wider mid-band replacement damages side/global metrics; narrower replacement reduces damage but remains worse than T7.
- Multi-solid output is not the decisive issue: T7 and normal slot1 templates are also multi-solid compounds.
- Do not continue simple radial-band transplant variants unless the tool is changed to produce a cleaner section-level rebuild rather than boolean patchwork.

## 2026-04-24 member5 section-source branch

Goal: test whether rebuilding member5 from its own isolated source-member submesh fixes the current worst T7 member without template transplanting.

Attempted but abandoned:

- `templM5_preferSub_root55` with `--refine-gap-fill-mm 6` plus template diagnostics exceeded 20 minutes and produced no final STEP/STL. It did create `output/member5_prefer_submesh/_member_src_submesh_5.stl`. The process later exited without final artifacts.

Successful simplified template:

- `output/templM5_preferSub_noGap.step`
- Built from template member 5, `--refine-use-member-submesh`, `--prefer-member-submesh-sections`, no gap fill.
- Template radial diagnostic `output/templM5_preferSub_noGap.template_diag.json`: front_proxy 0.6063, root 0.8885, mid 0.9512, tail 0.8867. This is better than earlier member5 template scan proxies, but it did not translate to full-wheel improvement.

Full-wheel candidates below T7:

- T42 `output/extrudeLoopT42_T7_m5PreferSubNoGap.step`: member5 only replaced by `templM5_preferSub_noGap.step`; metrics front 0.6528, side 0.7437, spoke 0.3904.
- T43 `output/extrudeLoopT43_T7_m5PreferSubNoGapRadP2.step`: same but member5 template shifted +2mm radial; metrics front 0.6521, side 0.7429, spoke 0.3817.
- T44 `output/extrudeLoopT44_T7_m5PreferSubNoGapRadM2.step`: same but shifted -2mm radial; metrics front 0.6541, side 0.7439, spoke 0.3423.

Visual diagnostics:

- `output/eval_stage_extrudeLoopT42_T7_m5PreferSubNoGap_vizonly/` shows member5 score improved only slightly (T7 0.896 -> T42 0.885), while member2 became second-worst. This confirms the strong isolated-template proxy is not sufficient for global acceptance.

Interpretation:

- Direct member5 submesh-derived sections improve the isolated member proxy, but the assembled wheel loses spoke overlap.
- Simple radial shifts do not recover the loss.
- Do not continue member5 direct preferSub/noGap variants unless the assembly/alignment interaction is changed or a metric that preserves the local proxy gain is introduced.

## 2026-04-24 additional attempts T45-T53

User asked to try more. Completed two additional groups after T42-T44:

Member5 preferSub section-source parameter sweep:

- T45 `output/extrudeLoopT45_T7_m5PreferSubRoot35NoGap.step`: root_keep 0.35, trim_root_intersection 0.35, spoke 0.3631. Front rose to 0.6584 but spoke regressed hard.
- T46 `output/extrudeLoopT46_T7_m5PreferSubRoot45NoGap.step`: root_keep 0.45, trim_root_intersection 0.45, spoke 0.3805.
- T47 `output/extrudeLoopT47_T7_m5PreferSubRoot55Trim35.step`: root_keep 0.55, trim_root_intersection 0.35, spoke 0.3631. Same score as T45, so low trim ratio appears to dominate over root_keep here.
- T48 `output/extrudeLoopT48_T7_m5PreferSubRoot55Trim75.step`: root_keep 0.55, trim_root_intersection 0.75, spoke 0.3452.
- T49 `output/extrudeLoopT49_T7_m5PreferSubLower0.step`: root_keep 0.55, trim 0.55, lower_strength 0.0, spoke 0.3926, side 0.7470. Best of this direct member5 branch but still below T7.
- T50 `output/extrudeLoopT50_T7_m5PreferSubLowerP12.step`: lower_strength +0.12, spoke 0.3597.

Visual diagnostics:

- `output/eval_stage_extrudeLoopT49_T7_m5PreferSubLower0_vizonly/` shows T49 does not truly improve member5: member7 becomes worst (score 0.989), member5 remains 0.899. This rejects lower0 despite decent side overlap.

Global angle micro-sweep on T7 templates:

- T51 `output/extrudeLoopT51_T7_globalAngM025.step`: global spoke offset -0.25 deg, spoke 0.3697.
- T52 `output/extrudeLoopT52_T7_globalAngP025.step`: global spoke offset +0.25 deg, spoke 0.3979.
- T53 `output/extrudeLoopT53_T7_globalAngP0125.step`: global spoke offset +0.125 deg, spoke 0.3591.

Conclusion:

- T7 remains best: spoke 0.4043.
- Direct member5 preferSub can improve isolated template diagnostics but fails full-wheel member diagnostics.
- Global angle offset is not the missing improvement; zero offset is still best among tested values.
- The only near-ish new candidate is T49, but visual diagnostics reject it because member7/member5 worsen.

## 2026-04-25 visual-defect pass and T54-T57

User explicitly redirected the work away from numeric-only tuning and asked to use more visual evidence.

Current best remains T7:

- `output/extrudeLoopT7_P1_m3radP1_m5radP2.step`
- Metrics: front 0.6547, side 0.7428, spoke 0.4043, fwd 3.2410, bwd 3.3574.

Visual root cause from T7:

- T7 overlays show continuous blue STL-only bands through the spoke mid-span, especially member7/member9/member5/member0/member8.
- Red STEP-only points concentrate around the outer/tail vertical connection and some root/tail patches.
- Added signed boundary deltas to `tools/diagnose_visual_spoke_differences.py` so the diagnostics report `mean_lower_delta_mm`, `mean_upper_delta_mm`, and `mean_center_delta_mm` in addition to absolute deltas.
- Signed T7 diagnostics at `output/visual_signed_T7_P1_m3radP1_m5radP2/` show the recurring defect is upper-boundary underbuild, not simple whole-spoke translation:
  - slot1 average upper delta -0.915 mm, width delta -1.119 mm, STL-only mid 182.
  - slot0 average upper delta -1.308 mm, width delta -1.372 mm, STEP-only tail 118.
  - member9 is the clearest narrow section: lower +0.91, upper -1.94, width -2.85.
  - member8: lower +0.29, upper -1.91, width -2.20.

Visual comparison of existing upper branches:

- T18 `output/extrudeLoopT18_T7_upper06.step` reduces some upper negative bias, but it pushes lower edges positive and leaves width negative. It shifts/warps the section instead of cleanly expanding the upper boundary.
- T26 `output/extrudeLoopT26_T7_m5Upper02.step` improves neither the systemic blue mid-band nor slot consistency; slot0 mid missing and slot1 tail extra worsen.

New attempts:

- T54 `output/extrudeLoopT54_T7_slot1MidUpper04Tail10.step`: new slot1 mid-only upper compensation with weaker/later tail. Metrics front 0.6561, side 0.7441, spoke 0.3730. Visual: slot0 artifacts improved in aggregate, but member5 worsened to score 0.916 and slot1 average score worsened. Rejected.
- T55 `output/extrudeLoopT55_T7_m9MidUpper04Tail10.step`: only member9 uses the new mid-upper/tail-late template. Metrics front 0.6578, side 0.7420, spoke 0.3752. Visual: member7 and slot0 blue bands worsen. Rejected.
- T56 `output/extrudeLoopT56_T7_slot0TailLate08.step`: M2/slot0 tail reduced and delayed. Metrics front 0.6527, side 0.7362, spoke 0.3689. Visual: red did not cleanly disappear; red mid/top arcs and blue lower arcs appeared. Tail defect is not just tail_strength too high. Rejected.
- T57 `output/extrudeLoopT57_T7_m9Upper06Only.step`: only member9 uses upper06 template. Metrics front 0.6569, side 0.7411, spoke 0.3483. Signed visual shows less mid blue locally but stronger tail/connection red and overall spoke metric collapse. Rejected.

Updated defect diagnosis:

- The persistent blue bands come from a narrow/low upper mid-span boundary. The STEP upper edge is below the STL upper edge across most members.
- The lower edge is usually close to the STL or slightly inside, so scaling/thickening both sides is risky.
- Tail red is partly a bridge/connection source problem, not a scalar tail-thickness problem; reducing tail strength alone creates new mid/top red and lower blue.
- Whole-template replacement or member-only transplant changes tail/root alignment and breaks other members, even when a local member visually improves.

Recommended next move:

- Stop angle-only, whole-template replacement, global upper-lift, and scalar tail-strength sweeps.
- Modify the section-generation logic so the upper boundary only is expanded in the mid-span window, preserving the lower boundary and tapering before the tail bridge.
- The change should be section-level and source-guided, not a rotated full-template transplant. Gate it with signed visual diagnostics before trusting global metrics.

## 2026-04-25 continued source-guided upper-boundary tests T58-T62

Code change:

- Added signed visual deltas to `tools/diagnose_visual_spoke_differences.py`.
- Added `--refine-planform-upper-only` to `tools/run_spoke_extrude_refine_array_model.py`.
- The new planform mode moves only the positive local-x/tangent boundary toward the member source planform, with lower boundary weight near zero. This was added because T7's visual problem is upper-boundary underbuild while lower edges are mostly close.

Experiments:

- T58 `output/extrudeLoopT58_T7_slot1PlanUpper035.step`: applied the new upper-only planform template to all slot1 overrides. Metrics front 0.6558, side 0.7293, spoke 0.3602. Rejected. Visual showed m7/m9 upper deltas improved, but m1/m5 and side geometry worsened.
- T59 `output/extrudeLoopT59_T7_m7m9PlanUpper035.step`: applied upper-only planform only to m7 and m9. Metrics front 0.6526, side 0.7446, spoke 0.3772, fwd 3.2147, bwd 3.3489. Rejected as a final candidate, but visually informative:
  - m7 STL-only mid dropped from 38 to 10; upper delta improved from -1.13 to +0.32.
  - m9 STL-only mid dropped from 51 to 6; upper delta improved from -1.94 to -0.05.
  - tail STEP-only exploded: m7 5 -> 40, m9 4 -> 49. The defect moved from mid blue to tail red.
- T60 `output/extrudeLoopT60_T7_m7m9PlanUpper035Tail08Late.step`: same m7/m9 upper-only planform, but reduced/delayed tail strength. Metrics front 0.6549, side 0.7473, spoke 0.3673. Rejected. Visual: tail changes brought the mid underbuild back; m7 STL-only mid 52, m9 37.
- T61 `output/extrudeLoopT61_T7_m7m9PlanUpper035BridgeNone.step`: same as T59 but `tip_bridge_mode=none`. Metrics and signed visual diagnostics were identical to T59. Tip bridge mode is not the active cause of the tail red.
- T62 `output/extrudeLoopT62_T7_m7m9PlanUpper035KeepTip82.step`: same as T59 but `keep_tip_shell` with ratio 0.82. Metrics were identical to T59/T61. This switch does not affect the relevant tail red in this template route.

Current visual diagnosis:

- The new upper-only planform mode validates the direction: source-guided upper-boundary expansion can remove the continuous mid-span blue bands on m7/m9.
- The blocker is now the tail/outer trim handoff. When the m7/m9 upper boundary is fixed, the model creates large STEP-only red near the tail/outer connection.
- Reducing tail thickness removes the support that kept the upper boundary corrected, so tail thickness is coupled with mid upper coverage in the current loft/trim construction.
- `tip_bridge_mode` and `keep_tip_shell` do not touch this defect; the red tail likely comes from the trim composition / refine-body outer handoff, not the optional bridge interpolation.

Recommended next move:

- Keep T7 as final best.
- Keep `--refine-planform-upper-only`; it is useful evidence and may be part of the eventual fix.
- Next implementation should introduce a tail-local trim or one-sided upper taper that clips/refuses the planform expansion after roughly station ratio 0.70-0.76 while preserving the mid-span correction. Do not lower global tail strength.
- More parameter sweeps on existing `tip_bridge`, `keep_tip_shell`, or `tail_strength` are unlikely to help.

## 2026-04-25 continued m9 radial-band donor tests T63-T67

Goal:

- Keep the proven m7/m9 upper-boundary correction from the planform donor, but prevent the tail red that appears when the donor owns the full spoke.

Additional tests:

- T63 `output/extrudeLoopT63_T7_m7m9PlanUpper035End064.step`: made the upper-only planform window end earlier at station ratio 0.64. Metrics front 0.6510, side 0.7352, spoke 0.3747. Visual: m7/m9 still had large tail red; early endpoint did not solve the tail handoff.
- T64 `output/extrudeLoopT64_T7_m7m9HybridPlanUpperBand105_148.step`: radial-band hybrid using the planUpper donor only in r=105-148mm; m7 base from `templLoopB7_intersect`, m9 base from `templLoopB7_rootIntReplace55`. Metrics front 0.6540, side 0.7431, spoke 0.3669. Visual: m9 improved strongly, m7 did not.
- T65 `output/extrudeLoopT65_T7_m9HybridPlanUpperBand105_148.step`: same hybrid only on m9. Metrics front 0.6550, side 0.7456, spoke 0.3809, fwd 3.2117, bwd 3.3575. Visual: m9 improved relative to T7 and tail stayed clean, but mid underbuild remained partially.
- T66 `output/extrudeLoopT66_T7_m9HybridPlanUpperBand098_156.step`: wider m9 hybrid band r=98-156mm. Metrics front 0.6576, side 0.7507, spoke 0.3630, fwd 3.2033, bwd 3.3467. Visual diagnostics are the strongest so far by member-score even though spoke_overlap is low:
  - T66 worst visual member score 0.830 versus T7 worst 0.896.
  - m9 score 0.603, stl_mid 13, upper -0.35; much cleaner than T7 m9 score 0.806, stl_mid 51, upper -1.94.
  - Full visual stage is at `output/eval_stage_extrudeLoopT66_T7_m9HybridPlanUpperBand098_156_vizonly/`.
- T67 `output/extrudeLoopT67_T7_m9HybridPlanUpperBand100_152.step`: intermediate band r=100-152mm. Metrics front 0.6535, side 0.7430, spoke 0.3729. Visual: m9 tail red rose to 56; rejected.

Current interpretation:

- T66 is not the numeric winner because spoke_overlap drops hard, but it is the best visual-diagnostic proof that targeted m9 mid-band donor replacement can reduce the systematic upper-edge blue defect.
- T65 is the safer numeric/visual compromise, but it under-corrects m9 mid-span.
- T67 shows the band blend is sensitive and not monotonic; continuing blind band sweeps is low value.
- The remaining issue is probably the boolean radial-band hybrid boundary itself. It can improve local member envelopes, but it may create front-view residuals that spoke_overlap punishes.

Recommended next move:

- Keep T7 as accepted best for now.
- Keep T66 as the main visual lead, not as final accepted output.
- Next useful implementation should replace boolean radial-band hybridization with a section-level donor splice inside `run_spoke_extrude_refine_array_model.py`: source only selected mid stations from the upper-only planform section loop, then loft one clean section sequence. This should avoid the hard radial cut seams from `hybridize_spoke_template_radial_band.py`.

## 2026-04-25 delivery-candidate pass T68-T74

Goal:

- Continue from the T66 visual lead and reach a deliverable candidate that improves the active T7 baseline without relying only on numeric tuning.

Tests:

- T68 `output/extrudeLoopT68_T7_m9Root55PlanUpperSpan098_156.step`: rebuilt a continuous root55 + upper-only planform loft instead of boolean band splicing. Metrics front 0.6559, side 0.7372, spoke 0.3638. Visual: m9 mid improved, but tail red remained and neighboring slot diagnostics worsened. Rejected.
- T69 `output/extrudeLoopT69_T7_m9HybridPlanUpperBand098_150.step`: m9-only radial-band hybrid, base `templLoopB7_rootIntReplace55`, donor `templB7_planUpperOnly035`, band 98-150mm, overlap 2mm. This is the current delivery candidate.
  - T69 metrics: front 0.6571, side 0.7410, spoke 0.4093, fwd 3.2708, bwd 3.3831.
  - T7 metrics: front 0.6547, side 0.7428, spoke 0.4043, fwd 3.2410, bwd 3.3574.
  - T69 beats T7 on front and spoke; side and NN regress slightly.
  - T69 full visual stage: `output/eval_stage_extrudeLoopT69_T7_m9HybridPlanUpperBand098_150_vizonly/`.
  - T69 worst visual score is 0.861 versus T7 worst 0.896, so the worst visible member defect is reduced.
- T70 `output/extrudeLoopT70_T7_m9HybridPlanUpperBand098_150ov1.step`: same as T69 but overlap 1mm. Metrics front 0.6591, side 0.7381, spoke 0.3785. Rejected.
- T71/T72: m9 hybrid angle offsets +/-0.5 deg. T71 spoke 0.4046, T72 spoke 0.3790. Neither beats T69.
- T73/T74: pre-rotated m9 hybrid with radial shifts +/-1mm. Front increased, but side and spoke regressed. Rejected.

Current accepted candidate:

- `output/extrudeLoopT69_T7_m9HybridPlanUpperBand098_150.step`

Why T69 is acceptable:

- It is the first candidate in this branch to beat T7's spoke metric while also improving front overlap.
- It reduces the worst visual member score relative to T7.
- It is narrowly scoped: only member9 changes; all other T7 member-template choices are preserved.

Known caveat:

- T69 still has a small side/NN regression and does not eliminate every blue mid-span band. It is an incremental delivery candidate, not a perfect final wheel.
- Further work should not continue cheap m9 angle/radial/overlap tweaks; the next real improvement requires a cleaner non-boolean section splice for the m9 donor band.
