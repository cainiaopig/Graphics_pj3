# Project: BlenderSceneAgent

## 1. Project Goal

We are building a lightweight agentic 3D scene generation system for a computer graphics course project.

The system should take a natural language prompt as input, convert it into a structured 3D scene graph, validate and optionally repair the scene graph, and finally generate a Blender scene using procedural Python functions.

The project should focus on building a clear, stable, and extensible framework first. Runtime AI models can be decided later. For now, implement mock agents and clean interfaces.

The final project should demonstrate the following pipeline:

```text
User Prompt
  -> Planner Agent
  -> Scene Graph JSON
  -> Validator Agent
  -> Optional Repair Agent
  -> Blender Scene Builder
  -> Rendered Image / Video / .blend File
```

The main idea is:

* LLMs are used for planning, validation, and repair.
* Blender Python is used for deterministic procedural scene construction.
* The system should not rely on LLMs directly writing arbitrary Blender code in the first version.
* The scene graph JSON acts as an intermediate representation between natural language and Blender procedural modeling.

---

## 2. Important Design Principles

### 2.1 Use Scene Graph Instead of Direct Code Generation

Do not design the system as:

```text
Prompt -> LLM directly writes full Blender Python code
```

Instead, design it as:

```text
Prompt -> LLM generates structured JSON -> Our Python builder generates Blender scene
```

This makes the system more stable, controllable, debuggable, and easier to evaluate.

### 2.2 Separate AI Planning from Blender Execution

The normal Python pipeline should be able to run without Blender and without external AI APIs.

The Blender-specific code should only be imported or executed inside scripts that run under Blender.

Avoid importing `bpy` in normal Python modules unless the file is specifically intended to be executed by Blender.

### 2.3 Use Mock Agents First

For the MVP, implement mock agents that return predefined scene graphs.

Do not require external API calls in the first working version.

Later, we will add real LLM backends such as DeepSeek, OpenAI-compatible APIs, Claude, Gemini, GLM, or other models.

### 2.4 Keep the First Version Procedural and Simple

The first version should use simple Blender primitives:

* cubes
* planes
* cylinders
* bevels if easy
* simple materials
* emissive materials
* point lights / area lights
* cameras

Do not use external 3D assets in the MVP.

Avoid Objaverse, online asset retrieval, or complex `.glb` importing in the first version.

### 2.5 The System Should Be Easy to Demonstrate

The final demo should show:

* input prompt
* generated scene graph JSON
* validation report
* repaired scene graph if applicable
* rendered Blender result
* multiple example scenes

---

## 3. Target MVP

The MVP should support the following command:

```bash
python main.py --prompt "Create a cozy cyberpunk bedroom with a bed, desk, monitor, neon lights, posters, carpet, and a window showing a futuristic city." --backend mock
```

The system should generate:

```text
outputs/
  scene_json/
    latest_scene_graph.json
    latest_repaired_scene_graph.json
  validation/
    latest_validation_report.json
  blender_scripts/
    latest_blender_scene.py
  renders/
    latest_render.png
  logs/
    latest_run.log
```

The Blender render step can be triggered with:

```bash
blender --background --python scripts/run_blender_scene.py -- --scene-json outputs/scene_json/latest_repaired_scene_graph.json --output outputs/renders/latest_render.png
```

The batch demo should support:

```bash
python scripts/batch_demo.py --backend mock
```

It should generate renders for multiple predefined prompts.

---

## 4. Repository Structure

Create the following project structure:

```text
blender-scene-agent/
  README.md
  CLAUDE.md
  requirements.txt
  .gitignore
  main.py

  configs/
    default.yaml

  prompts/
    planner_prompt.txt
    validator_prompt.txt
    repair_prompt.txt
    visual_critic_prompt.txt

  agents/
    __init__.py
    base_agent.py
    llm_client.py
    planner_agent.py
    validator_agent.py
    repair_agent.py
    visual_critic_agent.py

  schema/
    __init__.py
    scene_schema.py

  core/
    __init__.py
    pipeline.py
    json_utils.py
    logging_utils.py
    file_utils.py

  blender/
    __init__.py
    scene_builder.py
    primitives.py
    materials.py
    layout.py
    geometry_validator.py
    render_config.py

  scripts/
    run_blender_scene.py
    batch_demo.py
    export_turntable.py

  examples/
    prompts/
      cyberpunk_bedroom.txt
      cozy_study_room.txt
      modern_classroom.txt
      small_coffee_shop.txt
      sci_fi_laboratory.txt

    scene_graphs/
      cyberpunk_bedroom.json
      cozy_study_room.json
      modern_classroom.json
      small_coffee_shop.json
      sci_fi_laboratory.json

  outputs/
    scene_json/
    validation/
    blender_scripts/
    renders/
    videos/
    logs/

  tests/
    test_scene_schema.py
    test_validator.py
    test_layout.py

  report_assets/
    figures/
    tables/
```

---

## 5. Dependencies

Use Python 3.10+.

The first version should only require lightweight dependencies.

`requirements.txt` should include:

```text
pydantic>=2.0
pyyaml
python-dotenv
rich
pytest
```

Do not require Blender as a Python package. Blender will be called externally through the `blender` executable.

Optional future dependencies can be documented but should not be required in the MVP.

---

## 6. Scene Graph Schema

Implement the scene graph using Pydantic models in:

```text
schema/scene_schema.py
```

The schema should include the following models:

### 6.1 SceneGraph

Fields:

```python
scene_id: str
scene_type: str
style: list[str]
room: RoomConfig
objects: list[SceneObject]
relations: list[Relation]
lighting: LightingConfig
camera: CameraConfig
metadata: dict
```

### 6.2 RoomConfig

Fields:

```python
width: float
depth: float
height: float
floor_material: str
wall_material: str
```

Default room size:

```python
width = 6.0
depth = 5.0
height = 3.0
```

### 6.3 SceneObject

Fields:

```python
id: str
type: str
description: str
semantic_position: str
size: list[float]
material: str
color: str | None
rotation: list[float] | None
extra: dict
```

`size` should mean:

```text
[x_size, y_size, z_size]
```

### 6.4 Relation

Fields:

```python
subject: str
predicate: str
object: str
```

Supported relation predicates:

```text
on
near
left_of
right_of
in_front_of
behind
attached_to
inside
facing
```

### 6.5 LightingConfig

Fields:

```python
mood: str
main_colors: list[str]
brightness: str
use_emissive_lights: bool
```

### 6.6 CameraConfig

Fields:

```python
view: str
position: list[float]
target: list[float]
focal_length: float
resolution: list[int]
```

Default:

```python
position = [4.5, -5.0, 3.0]
target = [0.0, 0.0, 1.2]
focal_length = 28.0
resolution = [1280, 720]
```

---

## 7. Supported Scene Types

The MVP should focus on indoor scenes only.

Supported scene types:

```text
bedroom
study_room
classroom
coffee_shop
laboratory
generic_room
```

If the planner receives an unsupported scene type, it should map it to `generic_room`.

---

## 8. Supported Object Types

The MVP should support these object types:

### Architecture

```text
window
door
wall_decoration
```

The room itself is created automatically and should not need to appear as an object.

### Furniture

```text
bed
desk
chair
table
sofa
shelf
counter
bookshelf
```

### Small Objects and Decorations

```text
monitor
keyboard
lamp
plant
carpet
poster
blackboard
projector_screen
menu_board
glowing_tube
warning_sign
neon_light
book
cup
```

If an unsupported object type appears in the scene graph, the validator should report it.

The repair agent can either remove unsupported objects or map them to the closest supported type.

---

## 9. Example Scene Graph

Create this example file:

```text
examples/scene_graphs/cyberpunk_bedroom.json
```

Content:

```json
{
  "scene_id": "cyberpunk_bedroom_001",
  "scene_type": "bedroom",
  "style": ["cozy", "cyberpunk", "neon"],
  "room": {
    "width": 6.0,
    "depth": 5.0,
    "height": 3.0,
    "floor_material": "dark wood",
    "wall_material": "dark concrete"
  },
  "objects": [
    {
      "id": "bed_1",
      "type": "bed",
      "description": "a dark fabric bed with pillows",
      "semantic_position": "left side of the room",
      "size": [2.2, 1.4, 0.55],
      "material": "dark fabric",
      "color": "dark gray",
      "rotation": [0, 0, 0],
      "extra": {}
    },
    {
      "id": "desk_1",
      "type": "desk",
      "description": "a dark wooden computer desk",
      "semantic_position": "right side of the room",
      "size": [1.6, 0.7, 0.75],
      "material": "dark wood",
      "color": "black",
      "rotation": [0, 0, 0],
      "extra": {}
    },
    {
      "id": "monitor_1",
      "type": "monitor",
      "description": "a glowing computer monitor",
      "semantic_position": "on desk_1",
      "size": [0.8, 0.08, 0.45],
      "material": "black plastic and emissive screen",
      "color": "cyan",
      "rotation": [0, 0, 0],
      "extra": {}
    },
    {
      "id": "neon_1",
      "type": "neon_light",
      "description": "magenta and blue neon wall light",
      "semantic_position": "back wall",
      "size": [1.4, 0.05, 0.12],
      "material": "emissive",
      "color": "magenta",
      "rotation": [0, 0, 0],
      "extra": {}
    },
    {
      "id": "poster_1",
      "type": "poster",
      "description": "a futuristic wall poster",
      "semantic_position": "left wall",
      "size": [0.8, 0.03, 1.0],
      "material": "paper",
      "color": "blue",
      "rotation": [0, 0, 0],
      "extra": {}
    },
    {
      "id": "window_1",
      "type": "window",
      "description": "a window showing futuristic city lights outside",
      "semantic_position": "back wall",
      "size": [1.6, 0.05, 1.1],
      "material": "glass",
      "color": "cyan",
      "rotation": [0, 0, 0],
      "extra": {
        "outside_view": "futuristic city lights"
      }
    },
    {
      "id": "carpet_1",
      "type": "carpet",
      "description": "a soft carpet on the floor",
      "semantic_position": "center of the room",
      "size": [2.0, 1.5, 0.03],
      "material": "fabric",
      "color": "dark purple",
      "rotation": [0, 0, 0],
      "extra": {}
    }
  ],
  "relations": [
    {
      "subject": "monitor_1",
      "predicate": "on",
      "object": "desk_1"
    },
    {
      "subject": "neon_1",
      "predicate": "attached_to",
      "object": "back_wall"
    },
    {
      "subject": "poster_1",
      "predicate": "attached_to",
      "object": "left_wall"
    },
    {
      "subject": "window_1",
      "predicate": "attached_to",
      "object": "back_wall"
    },
    {
      "subject": "carpet_1",
      "predicate": "near",
      "object": "bed_1"
    }
  ],
  "lighting": {
    "mood": "cyberpunk",
    "main_colors": ["blue", "magenta"],
    "brightness": "medium",
    "use_emissive_lights": true
  },
  "camera": {
    "view": "wide angle",
    "position": [4.5, -5.0, 3.0],
    "target": [0.0, 0.0, 1.2],
    "focal_length": 28.0,
    "resolution": [1280, 720]
  },
  "metadata": {
    "source_prompt": "Create a cozy cyberpunk bedroom with a bed, desk, computer monitor, neon lights, posters, carpet, and a window showing a futuristic city.",
    "version": "mvp"
  }
}
```

---

## 10. Agent Design

Implement agents in the `agents/` directory.

### 10.1 BaseAgent

Create an abstract base class:

```python
class BaseAgent:
    def __init__(self, backend: str = "mock"):
        self.backend = backend
```

### 10.2 PlannerAgent

File:

```text
agents/planner_agent.py
```

Interface:

```python
class PlannerAgent(BaseAgent):
    def plan(self, user_prompt: str) -> SceneGraph:
        ...
```

Backends:

```text
mock
openai_compatible_placeholder
```

The mock backend should select one of the example scene graphs based on keywords in the prompt.

For example:

```text
bedroom -> cyberpunk_bedroom.json
study -> cozy_study_room.json
classroom -> modern_classroom.json
coffee -> small_coffee_shop.json
laboratory / lab -> sci_fi_laboratory.json
```

The OpenAI-compatible placeholder should not be fully required to run, but the interface should be ready for later:

```python
LLM_API_BASE
LLM_API_KEY
LLM_MODEL
```

Do not hardcode any provider name in the core logic.

### 10.3 ValidatorAgent

File:

```text
agents/validator_agent.py
```

Interface:

```python
class ValidatorAgent(BaseAgent):
    def validate(self, user_prompt: str, scene_graph: SceneGraph) -> ValidationReport:
        ...
```

Implement a rule-based validator first.

It should check:

1. Whether all object IDs are unique.
2. Whether object types are supported.
3. Whether relation predicates are supported.
4. Whether relation subjects refer to existing objects.
5. Whether relation objects refer to existing objects or valid room surfaces.
6. Whether important prompt keywords appear in the scene graph.
7. Whether style words are represented in the scene graph.
8. Whether each object has valid size values.
9. Whether camera and lighting are present.

The validation report should be saved as JSON.

### 10.4 RepairAgent

File:

```text
agents/repair_agent.py
```

Interface:

```python
class RepairAgent(BaseAgent):
    def repair(
        self,
        user_prompt: str,
        scene_graph: SceneGraph,
        validation_report: ValidationReport
    ) -> SceneGraph:
        ...
```

Implement simple rule-based repairs first:

* If poster is missing and the prompt mentions poster, add a poster to the wall.
* If carpet is missing and the prompt mentions cozy, add a carpet.
* If neon or cyberpunk is mentioned but no neon light exists, add a neon light.
* If monitor is mentioned but no desk exists, add a desk first.
* If monitor exists but has no `on desk` relation, add the relation.
* If unsupported object appears, map it to closest supported type if possible.

Later, this can be replaced with an LLM repair backend.

### 10.5 VisualCriticAgent

File:

```text
agents/visual_critic_agent.py
```

For MVP, create only a placeholder.

Interface:

```python
class VisualCriticAgent(BaseAgent):
    def critique(self, user_prompt: str, image_path: str) -> dict:
        ...
```

Return a mock critique for now.

Do not implement real image understanding in the MVP.

---

## 11. LLM Client Design

File:

```text
agents/llm_client.py
```

Create an OpenAI-compatible client wrapper, but do not make it required for MVP.

It should read environment variables:

```text
LLM_API_BASE
LLM_API_KEY
LLM_MODEL
```

Basic interface:

```python
class LLMClient:
    def __init__(self, api_base: str, api_key: str, model: str):
        ...

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict:
        ...
```

For now, this can be a placeholder or minimal implementation.

The project should run with:

```bash
python main.py --backend mock
```

without requiring any API key.

---

## 12. Prompt Templates

Create the following prompt files.

### 12.1 prompts/planner_prompt.txt

```text
You are a 3D scene planning agent.

Your task is to convert a natural language description into a structured JSON scene graph for a Blender procedural scene generator.

The generator only supports indoor scenes and a limited set of object types.

Supported scene types:
bedroom, study_room, classroom, coffee_shop, laboratory, generic_room

Supported object types:
bed, desk, chair, table, sofa, shelf, counter, bookshelf, monitor, keyboard, lamp, plant, carpet, poster, blackboard, projector_screen, menu_board, glowing_tube, warning_sign, neon_light, book, cup, window, door, wall_decoration

Supported relation predicates:
on, near, left_of, right_of, in_front_of, behind, attached_to, inside, facing

Rules:
1. Output valid JSON only.
2. Do not include markdown.
3. Do not invent unsupported object types.
4. Every object must include:
   id, type, description, semantic_position, size, material, color, rotation, extra.
5. The room must include:
   width, depth, height, floor_material, wall_material.
6. Include lighting and camera configuration.
7. Prefer simple, visually clear objects.
8. Keep the scene suitable for procedural Blender construction.

User prompt:
{user_prompt}
```

### 12.2 prompts/validator_prompt.txt

```text
You are a 3D scene validation agent.

Compare the original user prompt with the generated scene graph.

Check:
1. Important objects mentioned in the prompt.
2. Scene type correctness.
3. Style consistency.
4. Unsupported object types.
5. Invalid spatial relations.
6. Missing lighting or camera settings.
7. Objects with invalid size or missing fields.

Return valid JSON only with:
{
  "is_valid": boolean,
  "missing_objects": [],
  "unsupported_objects": [],
  "invalid_relations": [],
  "weak_style_elements": [],
  "suggestions": []
}

User prompt:
{user_prompt}

Scene graph:
{scene_graph}
```

### 12.3 prompts/repair_prompt.txt

```text
You are a scene graph repair agent.

Given the original user prompt, the current scene graph, and the validation feedback, repair the scene graph.

Rules:
1. Keep valid existing objects.
2. Add missing important objects.
3. Remove or replace unsupported objects.
4. Fix invalid relations.
5. Strengthen weak style elements using supported objects, materials, colors, or lights.
6. Return the full repaired scene graph as valid JSON only.
7. Do not include markdown.

User prompt:
{user_prompt}

Current scene graph:
{scene_graph}

Validation feedback:
{validation_report}
```

### 12.4 prompts/visual_critic_prompt.txt

```text
You are a visual critic for a Blender 3D scene generation system.

Given the original prompt and a rendered image, evaluate whether the image satisfies the prompt.

Check:
1. Object presence.
2. Spatial arrangement.
3. Style consistency.
4. Lighting quality.
5. Camera visibility.
6. Obvious geometry problems.

Return valid JSON only:
{
  "score": 1-10,
  "visible_objects": [],
  "missing_or_unclear_objects": [],
  "style_issues": [],
  "geometry_issues": [],
  "camera_issues": [],
  "repair_suggestions": []
}
```

---

## 13. Blender Scene Builder

Implement Blender-related modules inside:

```text
blender/
```

### 13.1 blender/primitives.py

This file should contain low-level primitive creation functions.

Functions:

```python
create_cube(
    name: str,
    location: tuple[float, float, float],
    scale: tuple[float, float, float],
    material_name: str | None = None
)

create_plane(...)
create_cylinder(...)
create_text(...)
```

### 13.2 blender/materials.py

Functions:

```python
create_material(name: str, color: tuple[float, float, float, float])
create_emissive_material(name: str, color: tuple[float, float, float, float], strength: float)
create_glass_material(name: str)
get_or_create_material(...)
```

### 13.3 blender/layout.py

This file converts semantic positions and relations into Blender coordinates.

Coordinate convention:

```text
x axis: left-right
y axis: front-back
z axis: height
room center: origin
floor: z = 0
back wall: y = room_depth / 2
front wall: y = -room_depth / 2
left wall: x = -room_width / 2
right wall: x = room_width / 2
```

Implement:

```python
estimate_initial_location(obj, room)
apply_relation_layout(objects, relations, room)
resolve_semantic_position(semantic_position, room)
```

Basic semantic positions:

```text
left side of the room
right side of the room
center of the room
back wall
front wall
left wall
right wall
on <object_id>
near <object_id>
```

### 13.4 blender/scene_builder.py

This is the main Blender construction file.

Functions:

```python
clear_scene()
build_scene(scene_graph: dict)
create_room(room_config)
create_object(scene_object)
setup_lighting(lighting_config)
setup_camera(camera_config)
save_blend_file(path)
render_image(output_path)
```

Object-specific functions:

```python
create_bed(obj)
create_desk(obj)
create_chair(obj)
create_table(obj)
create_sofa(obj)
create_shelf(obj)
create_bookshelf(obj)
create_counter(obj)
create_monitor(obj)
create_keyboard(obj)
create_lamp(obj)
create_plant(obj)
create_carpet(obj)
create_poster(obj)
create_blackboard(obj)
create_projector_screen(obj)
create_menu_board(obj)
create_glowing_tube(obj)
create_warning_sign(obj)
create_neon_light(obj)
create_book(obj)
create_cup(obj)
create_window(obj)
create_door(obj)
create_wall_decoration(obj)
```

Each object can be simple but should be visually recognizable.

Examples:

* Bed: base cube, mattress cube, pillow cubes.
* Desk: tabletop cube and four leg cubes.
* Chair: seat cube, back cube, four legs.
* Monitor: thin black frame cube, emissive screen cube, stand.
* Window: frame cubes, transparent glass, small emissive rectangles outside for city lights.
* Neon light: emissive cube or curve-like approximation, plus point/area light.
* Carpet: thin cube or plane.
* Plant: pot cylinder and simple green leaf shapes.
* Lamp: base, pole, lampshade, point light.
* Bookshelf: frame and small colored book cubes.
* Laboratory glowing tube: cylinder with emissive material.

---

## 14. Blender Runtime Script

Create:

```text
scripts/run_blender_scene.py
```

It should be executed by Blender.

Usage:

```bash
blender --background --python scripts/run_blender_scene.py -- --scene-json path/to/scene.json --output path/to/render.png
```

Responsibilities:

1. Parse command line arguments after `--`.
2. Load scene graph JSON.
3. Call Blender scene builder.
4. Set render engine.
5. Set resolution.
6. Render PNG.
7. Optionally save `.blend`.

The script should not require normal project pipeline code to import `bpy`.

---

## 15. Core Pipeline

Implement:

```text
core/pipeline.py
```

Main class:

```python
class SceneGenerationPipeline:
    def __init__(self, backend: str = "mock"):
        ...

    def run(self, user_prompt: str, output_dir: str = "outputs") -> dict:
        ...
```

Pipeline steps:

1. PlannerAgent generates initial scene graph.
2. Save initial scene graph.
3. ValidatorAgent validates it.
4. Save validation report.
5. If invalid, RepairAgent repairs it.
6. Save repaired scene graph.
7. Generate or call Blender render script.
8. Return paths to outputs.

The pipeline should work in mock mode without external API.

---

## 16. Main CLI

Implement:

```text
main.py
```

Usage:

```bash
python main.py --prompt "Create a cozy cyberpunk bedroom with neon lights." --backend mock
```

Optional arguments:

```text
--output-dir outputs
--skip-render
--render
--scene-json path/to/existing_scene.json
```

Behavior:

* If `--prompt` is provided, run full pipeline.
* If `--scene-json` is provided, skip planning and render existing scene graph.
* If `--skip-render` is set, only generate JSON and validation reports.
* If `--render` is set, attempt to call Blender executable.

Do not fail if Blender is not installed. Print a clear instruction instead.

---

## 17. Validation Report Schema

Create a simple model or dictionary for validation reports.

Fields:

```python
is_valid: bool
missing_objects: list[str]
unsupported_objects: list[str]
invalid_relations: list[str]
weak_style_elements: list[str]
suggestions: list[str]
warnings: list[str]
score: float
```

Save reports as JSON.

---

## 18. Geometry Validator

Implement:

```text
blender/geometry_validator.py
```

This module should not require Blender at first.

It can check simple layout-level issues:

1. Object sizes are positive.
2. Objects are inside room bounds.
3. Objects with `on` relation have plausible z positions.
4. Objects attached to walls have wall-like semantic positions.
5. Very large objects are flagged.

This can be approximate.

---

## 19. Example Prompts

Create these prompt files:

### cyberpunk_bedroom.txt

```text
Create a cozy cyberpunk bedroom with a bed, desk, computer monitor, neon lights, posters, carpet, and a window showing a futuristic city.
```

### cozy_study_room.txt

```text
Create a warm study room with a wooden desk, chair, bookshelf, table lamp, window, carpet, books, and wall paintings.
```

### modern_classroom.txt

```text
Create a modern classroom with desks, chairs, blackboard, projector screen, windows, and ceiling lights.
```

### small_coffee_shop.txt

```text
Create a small cozy coffee shop with round tables, chairs, counter, menu board, plants, pendant lamps, cups, and large windows.
```

### sci_fi_laboratory.txt

```text
Create a sci-fi laboratory with workbenches, monitors, glowing tubes, storage shelves, warning signs, and blue neon lights.
```

---

## 20. Batch Demo

Create:

```text
scripts/batch_demo.py
```

It should run the pipeline on all example prompts.

Outputs:

```text
outputs/batch/
  cyberpunk_bedroom/
    prompt.txt
    initial_scene_graph.json
    validation_report.json
    repaired_scene_graph.json
    render.png

  cozy_study_room/
    ...
```

The batch demo should be usable for final report figures and presentation slides.

---

## 21. README Requirements

Create a useful README.md with:

1. Project introduction.
2. Pipeline overview diagram in text.
3. Installation steps.
4. How to run mock pipeline.
5. How to render with Blender.
6. How to run batch demo.
7. Explanation of scene graph format.
8. Supported objects and relations.
9. Current limitations.
10. Future work.

Mention that this is a course project prototype and the first version uses procedural primitives.

---

## 22. Testing Requirements

Use pytest.

Create tests for:

### test_scene_schema.py

* example scene graph can be loaded.
* invalid object size fails or raises warning.
* unsupported relation is detected.

### test_validator.py

* missing object detection works.
* unsupported object detection works.
* invalid relation detection works.

### test_layout.py

* semantic positions resolve into plausible coordinates.
* `on` relation places object above target object.
* wall-attached objects are placed near walls.

Tests should not require Blender.

---

## 23. Development Order

Implement the project in this order:

### Step 1: Project Skeleton

Create the repository structure, empty modules, README, requirements, and example prompt files.

### Step 2: Scene Schema

Implement Pydantic scene graph models and JSON load/save utilities.

### Step 3: Example Scene Graphs

Create at least five valid example scene graphs.

### Step 4: Mock Planner Agent

Implement mock planner that maps prompt keywords to example scene graphs.

### Step 5: Validator Agent

Implement rule-based validation.

### Step 6: Repair Agent

Implement simple rule-based repair.

### Step 7: Core Pipeline

Connect planner, validator, repair, and file outputs.

### Step 8: Blender Scene Builder

Implement procedural Blender scene construction.

### Step 9: Blender Runtime Script

Implement command line rendering through Blender.

### Step 10: Batch Demo

Implement batch rendering and output organization.

### Step 11: Tests

Add unit tests for schema, validator, and layout.

### Step 12: Documentation Polish

Update README and add comments.

---

## 24. Acceptance Criteria for the First Framework Version

The framework is considered acceptable when:

1. `python main.py --prompt "...bedroom..." --backend mock --skip-render` runs successfully.
2. It generates scene graph JSON files.
3. It generates a validation report.
4. It optionally repairs the scene graph.
5. `pytest` passes.
6. At least one example JSON can be rendered by Blender.
7. `scripts/batch_demo.py` can process five prompts.
8. The code is modular and does not hardcode a specific LLM provider.
9. The project can run without any API key in mock mode.
10. README explains how to use the project.

---

## 25. Things Not to Implement Yet

Do not implement these in the first framework version:

1. Online asset retrieval.
2. Objaverse integration.
3. Complex 3D model importing.
4. Real visual critic with image input.
5. Full automatic video generation.
6. Training any model.
7. Physics simulation.
8. Human evaluation UI.
9. Web frontend.
10. Direct arbitrary Blender code generation from LLM.

These can be listed as future work.

---

## 26. Future Extensions

After the framework is complete, we may add:

1. Real LLM planner using an OpenAI-compatible API.
2. Real LLM validator.
3. Real LLM repair agent.
4. VLM-based visual critic.
5. Turntable video export.
6. More object types.
7. External 3D assets.
8. More realistic materials.
9. Collision-aware layout.
10. Multi-view rendering and evaluation.

---

## 27. Coding Style

Use:

* clear type hints
* small functions
* readable module boundaries
* meaningful logs
* JSON outputs for every intermediate result
* defensive error handling
* no hidden API dependencies
* no hardcoded absolute paths

Prefer simple and robust code over clever code.

---

## 28. First Task for Claude Code

Start by creating the project skeleton and implementing only the mock, non-Blender parts:

1. Create directory structure.
2. Implement Pydantic scene schema.
3. Implement JSON utilities.
4. Add example prompt files.
5. Add one complete example scene graph: cyberpunk bedroom.
6. Implement mock planner.
7. Implement rule-based validator.
8. Implement rule-based repair.
9. Implement main pipeline with `--skip-render`.
10. Add basic tests.

Do not implement real LLM API calls yet.

Do not implement complex Blender objects yet.

After this first task, the command below should work:

```bash
python main.py --prompt "Create a cozy cyberpunk bedroom with a bed, desk, monitor, neon lights, posters, carpet, and a window showing a futuristic city." --backend mock --skip-render
```

It should create output JSON files and validation reports.
