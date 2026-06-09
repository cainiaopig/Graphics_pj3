# BlenderSceneAgent

一个轻量级的智能体驱动 3D 场景生成系统。

**流水线：** 用户提示词 → Planner Agent → 场景图 JSON → Validator Agent → (Repair Agent) → Blender 场景构建 → 渲染图像

## 流水线概览

```text
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  用户提示词    │ ──▶ │ Planner Agent │ ──▶ │  场景图 JSON   │
│  (自然语言)    │     │ (mock/LLM)   │     │  (中间表示)     │
└──────────────┘     └──────────────┘     └──────┬────────┘
                                                  │
                                          ┌───────▼────────┐
                                          │ Validator Agent │
                                          │   (规则校验)     │
                                          └───────┬────────┘
                                                  │
                                          ┌───────▼────────┐
                                          │ Repair Agent    │
                                          │   (规则修复)     │
                                          └───────┬────────┘
                                                  │
                                          ┌───────▼────────┐
                                          │ Blender 场景    │
                                          │   构建器        │
                                          └───────┬────────┘
                                                  │
                                          ┌───────▼────────┐
                                          │  渲染图像 /     │
                                          │  .blend 文件    │
                                          └────────────────┘
```

### 核心设计理念

- **LLM** 仅用于规划（planning）、校验（validation）和修复（repair）
- **Blender Python** 用于确定性的程序化场景构建
- **场景图 JSON** 是自然语言与 Blender 之间的中间表示（IR）
- 系统**不会**让 LLM 直接编写任意的 Blender 代码——这保证了稳定性和可调试性
- **Blender 模块与普通 Python 模块严格隔离**——`bpy` 仅在 Blender 运行时环境中被导入，不在普通 Python 脚本中导入

## 安装

```bash
# 环境要求：Python 3.10+
pip install -r requirements.txt
```

依赖项（均为轻量级）：
- `pydantic>=2.0` — 数据模型与校验
- `pyyaml` — 配置文件解析
- `python-dotenv` — 环境变量管理
- `rich` — 终端美化输出
- `pytest` — 单元测试

## 快速开始（Mock 模式 — 无需 API Key）

```bash
# 运行完整流水线（跳过 Blender 渲染）：
python main.py --prompt "Create a cozy cyberpunk bedroom with a bed, desk, monitor, neon lights, posters, carpet, and a window showing a futuristic city." --backend mock --skip-render
```

运行后会在 `outputs/` 目录下生成：
- `outputs/scene_json/latest_scene_graph.json` — 初始场景图
- `outputs/scene_json/latest_repaired_scene_graph.json` — 修复后的场景图（如有需要）
- `outputs/validation/latest_validation_report.json` — 校验报告
- `outputs/logs/latest_run.log` — 运行日志

## 使用 Blender 渲染

需要安装 [Blender](https://www.blender.org/)（建议 3.0+），并确保 `blender` 命令在 PATH 中可用。

```bash
# 方式一：使用 --render 参数（自动调用 Blender）
python main.py --prompt "Create a cozy cyberpunk bedroom..." --backend mock --render

# 方式二：直接调用 Blender（快速预览，EEVEE 渲染器）
blender --background --python scripts/run_blender_scene.py -- \
    --scene-json outputs/scene_json/latest_repaired_scene_graph.json \
    --output outputs/renders/latest_render.png

# 方式三：高质量渲染（Cycles 渲染器，256 采样）
blender --background --python scripts/run_blender_scene.py -- \
    --scene-json outputs/scene_json/latest_scene_graph.json \
    --output outputs/renders/high_quality.png \
    --engine CYCLES --samples 256

# 同时保存 .blend 工程文件
blender --background --python scripts/run_blender_scene.py -- \
    --scene-json outputs/scene_json/latest_scene_graph.json \
    --output outputs/renders/render.png \
    --save-blend outputs/blender_scripts/scene.blend

# 自定义分辨率（覆盖场景图中的相机设置）
blender --background --python scripts/run_blender_scene.py -- \
    --scene-json outputs/scene_json/latest_scene_graph.json \
    --output outputs/renders/render_4k.png \
    --resolution 3840 2160 --engine CYCLES --samples 512
```

如果 Blender 未安装，`--render` 参数会打印清晰的调用指令，不会报错退出。

## 批量演示

```bash
python scripts/batch_demo.py --backend mock
```

处理 `examples/prompts/` 下的全部 5 个示例提示词，输出组织在 `outputs/batch/<scene_name>/` 下：

```text
outputs/batch/
  cyberpunk_bedroom/
    prompt.txt
    initial_scene_graph.json
    validation_report.json
    repaired_scene_graph.json
    pipeline_results.json
  cozy_study_room/
    ...
  modern_classroom/
    ...
  small_coffee_shop/
    ...
  sci_fi_laboratory/
    ...
```

## CLI 参数说明

```bash
python main.py [OPTIONS]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--prompt, -p` | 自然语言场景描述 | 无（与 `--scene-json` 二选一） |
| `--backend, -b` | Agent 后端：`mock` 或 `openai_compatible` | `mock` |
| `--output-dir, -o` | 输出根目录 | `outputs` |
| `--skip-render` | 跳过 Blender 渲染（默认开启） | `True` |
| `--render` | 尝试调用 Blender 渲染 | `False` |
| `--scene-json` | 使用已有场景图 JSON（跳过规划阶段） | 无 |

## 场景图格式

场景图 JSON 是整个系统的核心中间表示。各字段说明：

| 字段 | 说明 |
|------|------|
| `scene_id` | 场景唯一标识符 |
| `scene_type` | 场景类型（如 bedroom, laboratory） |
| `style` | 风格关键词列表（如 ["cozy", "cyberpunk", "neon"]） |
| `room` | 房间尺寸与材质（width, depth, height, floor_material, wall_material） |
| `objects` | 场景中所有物体的列表 |
| `relations` | 物体之间的空间关系列表 |
| `lighting` | 光照配置（mood, main_colors, brightness, use_emissive_lights） |
| `camera` | 相机配置（position, target, focal_length, resolution） |
| `metadata` | 元数据（source_prompt, version 等） |

每个物体的字段：

| 字段 | 说明 | 示例 |
|------|------|------|
| `id` | 唯一标识符 | `"bed_1"` |
| `type` | 物体类型 | `"bed"` |
| `description` | 文字描述 | `"a dark fabric bed with pillows"` |
| `semantic_position` | 语义位置 | `"left side of the room"` |
| `size` | 尺寸 [x, y, z]（米） | `[2.2, 1.4, 0.55]` |
| `material` | 材质名称 | `"dark fabric"` |
| `color` | 颜色 | `"dark gray"` |
| `rotation` | 旋转角 [rx, ry, rz]（弧度） | `[0, 0, 0]` |
| `extra` | 额外属性 | `{"outside_view": "futuristic city lights"}` |

### 支持的物体类型

**建筑元素：** `window`（窗户）, `door`（门）, `wall_decoration`（墙面装饰）

**家具：** `bed`（床）, `desk`（书桌）, `chair`（椅子）, `table`（桌子）, `sofa`（沙发）, `shelf`（搁架）, `counter`（柜台）, `bookshelf`（书架）

**小物件与装饰：** `monitor`（显示器）, `keyboard`（键盘）, `lamp`（灯）, `plant`（植物）, `carpet`（地毯）, `poster`（海报）, `blackboard`（黑板）, `projector_screen`（投影幕布）, `menu_board`（菜单牌）, `glowing_tube`（发光管）, `warning_sign`（警告标志）, `neon_light`（霓虹灯）, `book`（书）, `cup`（杯子）

### 支持的空间关系

`on`（在…上面）, `near`（靠近）, `left_of`（在…左边）, `right_of`（在…右边）, `in_front_of`（在…前面）, `behind`（在…后面）, `attached_to`（附着于）, `inside`（在…内部）, `facing`（面向）

### 支持的场景类型

`bedroom`（卧室）, `study_room`（书房）, `classroom`（教室）, `coffee_shop`（咖啡店）, `laboratory`（实验室）, `generic_room`（通用房间）

## 项目结构

```text
blender-scene-agent/
  main.py                      # CLI 入口
  README.md                    # 项目文档（本文件）
  CLAUDE.md                    # 详细设计文档（英文）
  requirements.txt             # Python 依赖
  .gitignore                   # Git 忽略规则

  configs/
    default.yaml               # 默认配置（支持的类型、关系、渲染参数等）

  prompts/                     # LLM 提示词模板
    planner_prompt.txt         # 规划 Agent 的 system prompt
    validator_prompt.txt       # 校验 Agent 的 system prompt
    repair_prompt.txt          # 修复 Agent 的 system prompt
    visual_critic_prompt.txt   # 视觉评判 Agent 的 system prompt

  schema/
    __init__.py
    scene_schema.py            # Pydantic 数据模型（SceneGraph, SceneObject 等）

  core/
    __init__.py
    pipeline.py                # 主流水线编排（Plan → Validate → Repair → Render）
    json_utils.py              # JSON 读写工具
    file_utils.py              # 文件系统工具（目录创建、时间戳、符号链接）
    logging_utils.py           # 日志配置

  agents/
    __init__.py
    base_agent.py              # Agent 抽象基类
    llm_client.py              # OpenAI 兼容的 LLM 客户端（MVP 中为占位）
    planner_agent.py           # 规划 Agent（mock: 关键词匹配示例场景图）
    validator_agent.py         # 校验 Agent（9 项基于规则的检查）
    repair_agent.py            # 修复 Agent（5 类基于规则的修复）
    visual_critic_agent.py     # 视觉评判 Agent（占位，未来接入 VLM）

  blender/                     # Blender 程序化模块（仅在 Blender 内使用）
    __init__.py
    primitives.py              # 基础图元（cube, plane, cylinder, sphere, cone, light）
    materials.py               # 材质工具（颜色解析、漫反射/发光/玻璃材质）
    layout.py                  # 布局计算（语义位置→3D 坐标，关系解析）
    scene_builder.py           # 场景构建主模块（房间、25 种物体、光照、相机）
    geometry_validator.py      # 几何校验（非 Blender 依赖）
    render_config.py           # 渲染配置（引擎、分辨率、采样、世界背景）

  scripts/
    run_blender_scene.py       # Blender 运行时脚本（加载 JSON → 构建场景 → 渲染）
    batch_demo.py              # 批量演示脚本（处理全部示例提示词）
    export_turntable.py        # 旋转视频导出（占位，未来实现）

  examples/
    prompts/                   # 5 个示例提示词
      cyberpunk_bedroom.txt
      cozy_study_room.txt
      modern_classroom.txt
      small_coffee_shop.txt
      sci_fi_laboratory.txt
    scene_graphs/              # 5 个对应的示例场景图 JSON
      cyberpunk_bedroom.json
      cozy_study_room.json
      modern_classroom.json
      small_coffee_shop.json
      sci_fi_laboratory.json

  tests/
    __init__.py
    test_scene_schema.py       # 场景 Schema 测试（模型创建、示例加载、字段校验）
    test_validator.py          # 校验器测试（缺失检测、不支持类型、无效关系等）
    test_layout.py             # 布局测试（语义位置解析、关系布局计算）

  outputs/                     # 生成的文件（自动创建）
    scene_json/                # 场景图 JSON
    validation/                # 校验报告 JSON
    blender_scripts/           # .blend 文件
    renders/                   # 渲染图像 PNG
    videos/                    # 视频（未来）
    logs/                      # 运行日志
    batch/                     # 批量演示输出

  report_assets/               # 课程报告素材（未来使用）
    figures/
    tables/
```

## 测试

```bash
# 运行全部测试
pytest tests/ -v

# 仅运行场景 schema 测试
pytest tests/test_scene_schema.py -v

# 仅运行校验器测试
pytest tests/test_validator.py -v

# 仅运行布局测试
pytest tests/test_layout.py -v
```

测试覆盖范围：
- **场景 Schema**：Pydantic 模型创建、默认值、5 个示例场景图的加载与字段完整性
- **校验器**：缺失物体检测、不支持类型检测、无效关系检测、重复 ID 检测、非法尺寸警告、风格覆盖检查、房间表面关系合法性
- **布局**：9 种语义位置解析（left wall, center, ceiling 等）、`on` 关系高度计算、`attached_to` 墙壁吸附、`left_of` / `near` 位置调整

所有测试**不需要 Blender**，可直接在普通 Python 环境中运行。

## Blender 渲染细节

### 房间构建（舞台布景模式）

房间采用"舞台布景"模式构建——只创建地板、天花板和三面墙（后墙、左墙、右墙）。**正面墙壁有意省略**，使放置在房间外的相机能够无障碍地观察室内场景。这是建筑可视化的常见做法。

### 坐标约定

```text
x 轴：左右方向（正值 = 右）
y 轴：前后方向（正值 = 后）
z 轴：高度方向（正值 = 上）
房间中心：原点 (0, 0)
地面：z = 0
后墙：y = +depth/2
前墙：y = -depth/2（不创建实体墙）
左墙：x = -width/2
右墙：x = +width/2
```

### 渲染器选择

| 渲染器 | 速度 | 质量 | 适用场景 |
|--------|------|------|----------|
| `BLENDER_EEVEE`（默认） | 快（秒级） | 实时预览级 | 快速迭代、批量演示 |
| `CYCLES` | 慢（分钟级） | 光线追踪级 | 最终展示、报告配图 |

### 发光物体

当场景图 `lighting.use_emissive_lights` 为 `true` 时，以下类型的物体会自动附加点光源：
- `neon_light`（霓虹灯）— 发光材质 + 同色点光源
- `glowing_tube`（发光管）— 发光材质 + 同色点光源
- `monitor`（显示器）— 发光屏幕材质
- `lamp`（灯具）— 自动添加暖色点光源

## 当前限制（MVP）

- **Mock Planner** 使用关键词匹配选择示例场景图，而非真正的 LLM 推理
- Blender 物体使用简单图元（立方体、圆柱、平面）近似表示，细节有限
- 无碰撞检测或高级布局优化
- 不使用外部 3D 资产（无 Objaverse 集成）
- Visual Critic 为占位实现（未来接入 VLM）
- 仅支持室内场景

## 未来工作

- [ ] 接入真实 LLM 后端（OpenAI 兼容 API、DeepSeek、Claude 等）
- [ ] LLM 驱动的校验与修复 Agent
- [ ] VLM 驱动的视觉评判（输入渲染图像，输出评估报告）
- [ ] 360° 旋转视频导出
- [ ] 更多物体类型与更真实的材质
- [ ] 碰撞感知的布局优化
- [ ] 多视角渲染与评估
- [ ] Web 前端交互式场景设计
- [ ] 外部 3D 模型导入（.glb / .obj）
- [ ] 物理模拟

## 开发说明

### 设计原则

1. **场景图优于直接代码生成** — LLM 不直接写 Blender 代码，而是生成结构化 JSON
2. **AI 规划与 Blender 执行分离** — 普通 Python 流水线可在无 Blender 环境下运行
3. **Mock 优先** — 第一个版本不依赖外部 API，全部使用规则和示例数据
4. **简单稳健优于聪明复杂** — MVP 使用程序化图元，逐步迭代改进
5. **模块隔离** — Blender 代码的 `bpy` 导入完全惰性化，不影响普通 Python 模块

### 添加新物体类型

1. 在 `configs/default.yaml` 的 `supported_object_types` 中添加类型名
2. 在 `blender/scene_builder.py` 的 `_create_object()` 的 `creators` 字典中注册
3. 实现 `_make_<type>()` 函数，使用 `blender.primitives` 中的图元
4. 在 `examples/scene_graphs/` 的示例 JSON 中添加使用该类型的物体实例

---

*第一版使用程序化图元和 Mock Agent，后续版本将逐步接入真实 LLM API。*
