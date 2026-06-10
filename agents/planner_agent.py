"""Planner agent that converts natural language prompts into scene graphs.

Supports two backends:
- mock: Keyword-based selection from example scene graphs.
- openai_compatible: Real LLM-based planning via any OpenAI-compatible API.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from agents.base_agent import BaseAgent
from agents.llm_client import LLMClient
from core.json_utils import load_json
from schema.scene_schema import (
    CameraConfig,
    LightingConfig,
    Relation,
    RoomConfig,
    SceneGraph,
    SceneObject,
)

logger = logging.getLogger(__name__)

# Mapping from prompt keywords to example scene graph files
KEYWORD_TO_SCENE: dict[str, str] = {
    "bedroom": "cyberpunk_bedroom.json",
    "study": "cozy_study_room.json",
    "classroom": "modern_classroom.json",
    "coffee": "small_coffee_shop.json",
    "laboratory": "sci_fi_laboratory.json",
    "lab": "sci_fi_laboratory.json",
}


PROMPT_OBJECT_PATTERNS: dict[str, tuple[str, ...]] = {
    "bed": ("bed", "patient bed"),
    "desk": ("desk", "workbench", "workbenches", "teacher desk", "l-shaped desk"),
    "chair": ("chair", "chairs", "gaming chair", "floor cushion", "floor cushions"),
    "table": ("table", "tables", "coffee table", "low table", "work table", "central table"),
    "sofa": ("sofa", "couch", "living room", "tea room"),
    "shelf": ("shelf", "shelves", "storage shelf", "storage shelves"),
    "counter": ("counter",),
    "bookshelf": ("bookshelf", "book shelf", "bookcase"),
    "monitor": ("monitor", "monitors", "computer monitor", "tv"),
    "keyboard": ("keyboard",),
    "lamp": ("lamp", "lamps", "light", "lights", "ceiling light", "pendant lamp", "candle", "candles"),
    "plant": ("plant", "plants"),
    "carpet": ("carpet", "rug", "tatami"),
    "poster": ("poster", "posters", "painting", "paintings", "framed paintings"),
    "blackboard": ("blackboard",),
    "projector_screen": ("projector screen", "projector_screen"),
    "menu_board": ("menu board", "menu_board"),
    "glowing_tube": ("glowing tube", "glowing tubes", "holographic", "crystal ball"),
    "warning_sign": ("warning sign", "warning signs"),
    "neon_light": ("neon", "neon light", "neon lights", "magical light"),
    "book": ("book", "books"),
    "cup": ("cup", "cups"),
    "window": ("window", "windows"),
    "door": ("door",),
    "wall_decoration": ("wall decoration", "wall decorations", "symbol", "symbols", "painting", "paintings"),
}

OBJECT_DEFAULTS: dict[str, dict[str, object]] = {
    "bed": {"size": [2.2, 1.4, 0.55], "material": "fabric", "color": "dark gray", "position": "left side of the room"},
    "desk": {"size": [1.6, 0.7, 0.75], "material": "wood", "color": "brown", "position": "right side of the room"},
    "chair": {"size": [0.5, 0.5, 0.9], "material": "wood and fabric", "color": "dark brown", "position": "in front of desk_1"},
    "table": {"size": [1.2, 0.8, 0.75], "material": "wood", "color": "brown", "position": "center of the room"},
    "sofa": {"size": [1.8, 0.8, 0.75], "material": "fabric", "color": "warm gray", "position": "back wall"},
    "shelf": {"size": [1.0, 0.3, 1.5], "material": "wood", "color": "brown", "position": "left wall"},
    "counter": {"size": [1.8, 0.7, 1.1], "material": "wood", "color": "dark brown", "position": "back wall"},
    "bookshelf": {"size": [0.9, 0.35, 1.8], "material": "wood", "color": "brown", "position": "left wall"},
    "monitor": {"size": [0.8, 0.08, 0.45], "material": "plastic and emissive screen", "color": "cyan", "position": "on desk_1"},
    "keyboard": {"size": [0.5, 0.15, 0.03], "material": "plastic", "color": "black", "position": "on desk_1"},
    "lamp": {"size": [0.2, 0.2, 0.4], "material": "metal and glass", "color": "warm white", "position": "on desk_1"},
    "plant": {"size": [0.35, 0.35, 0.6], "material": "ceramic and leaves", "color": "green", "position": "front-right corner"},
    "carpet": {"size": [2.0, 1.5, 0.03], "material": "woven fabric", "color": "deep red", "position": "center of the room"},
    "poster": {"size": [0.7, 0.03, 0.8], "material": "paper", "color": "blue", "position": "back wall"},
    "blackboard": {"size": [2.5, 0.05, 1.2], "material": "slate", "color": "dark green", "position": "back wall"},
    "projector_screen": {"size": [2.0, 0.04, 1.1], "material": "vinyl", "color": "white", "position": "back wall"},
    "menu_board": {"size": [1.0, 0.03, 0.7], "material": "painted board", "color": "black", "position": "back wall"},
    "glowing_tube": {"size": [0.8, 0.06, 0.06], "material": "emissive glass", "color": "blue", "position": "on desk_1"},
    "warning_sign": {"size": [0.4, 0.03, 0.3], "material": "painted metal", "color": "yellow", "position": "back wall"},
    "neon_light": {"size": [1.2, 0.05, 0.12], "material": "emissive", "color": "magenta", "position": "back wall"},
    "book": {"size": [0.2, 0.14, 0.03], "material": "paper", "color": "red", "position": "on desk_1"},
    "cup": {"size": [0.08, 0.08, 0.12], "material": "ceramic", "color": "white", "position": "on table_1"},
    "window": {"size": [1.5, 0.05, 1.0], "material": "glass", "color": "white", "position": "right wall"},
    "door": {"size": [0.9, 0.06, 2.1], "material": "wood", "color": "brown", "position": "front wall"},
    "wall_decoration": {"size": [0.6, 0.03, 0.6], "material": "canvas", "color": "gold", "position": "back wall"},
}

WALL_OBJECT_TYPES = {
    "window", "poster", "blackboard", "projector_screen", "menu_board",
    "warning_sign", "neon_light", "wall_decoration",
}
ON_OBJECT_TYPES = {"monitor", "keyboard", "lamp", "book", "cup", "glowing_tube"}
STYLE_KEYWORDS = {
    "artist", "cozy", "cyberpunk", "dense", "futuristic", "japanese", "magical",
    "medical", "modern", "sci-fi", "sci fi", "warm", "wizard",
}

# ---------------------------------------------------------------------------
# LLM system prompt for planning
# ---------------------------------------------------------------------------

PLANNER_SYSTEM_PROMPT = """You are a 3D scene planning agent for a Blender procedural scene generator.

Your ONLY task is to convert a natural language description into a structured JSON scene graph.
You MUST output ONLY valid JSON — no markdown, no explanations, no code fences.

## Supported Scene Types
bedroom, study_room, classroom, coffee_shop, laboratory, generic_room

## Supported Object Types (25 types)
bed, desk, chair, table, sofa, shelf, counter, bookshelf, monitor, keyboard,
lamp, plant, carpet, poster, blackboard, projector_screen, menu_board,
glowing_tube, warning_sign, neon_light, book, cup, window, door, wall_decoration

## Supported Relations (9 types)
on, near, left_of, right_of, in_front_of, behind, attached_to, inside, facing

## Room Surfaces (for attached_to relations)
back_wall, front_wall, left_wall, right_wall, ceiling, floor

## Size Guidelines (in meters [x, y, z])
- bed: [2.2, 1.4, 0.55]
- desk/table: [1.6, 0.7, 0.75]
- chair: [0.5, 0.5, 0.9]
- monitor: [0.8, 0.08, 0.45]
- bookshelf/shelf: [1.0, 0.3, 2.0]
- carpet: [2.0, 1.5, 0.03]
- window: [1.6, 0.05, 1.1]
- poster: [0.8, 0.03, 1.0]
- lamp: [0.2, 0.2, 0.5]
- plant: [0.3, 0.3, 0.8]
- neon_light: [1.4, 0.05, 0.12]
- blackboard: [3.0, 0.05, 1.2]
- door: [1.0, 0.05, 2.2]
- book: [0.2, 0.15, 0.03]
- cup: [0.08, 0.08, 0.12]
- Use reasonable sizes for other types.

## Room Guidelines
- Default room: 6m wide (x), 5m deep (y), 3m high (z)
- Adjust room size to fit the number of objects (larger for many objects)

## Material Guidelines
Use descriptive material names: "wood", "dark wood", "metal", "glass", "fabric",
"dark fabric", "leather", "plastic", "paper", "emissive", "paint", "tile", "marble".

## Color Guidelines
Use descriptive color names: "dark gray", "brown", "white", "black", "red",
"blue", "green", "cyan", "magenta", "yellow", "warm white", "wood brown".

## JSON Structure (MUST follow exactly)
{
  "scene_id": "snake_case_name",
  "scene_type": "one of the supported types above",
  "style": ["style1", "style2"],
  "room": {
    "width": 6.0,
    "depth": 5.0,
    "height": 3.0,
    "floor_material": "wood",
    "wall_material": "paint"
  },
  "objects": [
    {
      "id": "unique_snake_case_id",
      "type": "one of the 25 supported types",
      "description": "brief description",
      "semantic_position": "e.g. left wall, center of room, on desk_1",
      "size": [x, y, z],
      "material": "material name",
      "color": "color name",
      "rotation": [rx, ry, rz],
      "extra": {}
    }
  ],
  "relations": [
    {
      "subject": "object_id",
      "predicate": "on|near|left_of|right_of|in_front_of|behind|attached_to|inside|facing",
      "object": "target_object_id_or_room_surface"
    }
  ],
  "lighting": {
    "mood": "descriptive mood",
    "main_colors": ["color1", "color2"],
    "brightness": "low|medium|high",
    "use_emissive_lights": true_or_false
  },
  "camera": {
    "view": "perspective",
    "position": [4.5, -5.0, 3.0],
    "target": [0.0, 0.0, 1.2],
    "focal_length": 28.0,
    "resolution": [1280, 720]
  },
  "metadata": {}
}

## CRITICAL RULES
1. Output VALID JSON ONLY — no markdown, no backticks, no extra text.
2. EVERY object MUST have ALL fields: id, type, description, semantic_position, size, material, color, rotation, extra.
3. Use ONLY the 25 supported object types listed above — NEVER invent new types.
4. Use ONLY the 9 supported relation predicates.
5. Floor objects (bed, desk, chair, table, carpet, etc.) should sit on the floor.
6. Wall objects (window, poster, blackboard, neon_light, etc.) should use "attached_to" relations with a wall surface.
7. Monitors, keyboards, books, cups should use "on" relations (placed on desks/tables/shelves).
8. Create 5-10 objects for a typical scene.
9. EVERY object id MUST be unique.
10. scene_id should be descriptive and use snake_case."""


class PlannerAgent(BaseAgent):
    """Agent responsible for generating a SceneGraph from a user prompt.

    In mock mode, it selects the best-matching example scene graph based on
    keyword matching against the prompt text.

    In openai_compatible mode, it uses a real LLM to generate novel scene graphs.
    """

    def __init__(
        self,
        backend: str = "mock",
        examples_dir: str | Path | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        model: str | None = None,
    ) -> None:
        """Initialize the planner.

        Args:
            backend: Backend mode ("mock" or "openai_compatible").
            examples_dir: Directory containing example scene graph JSON files.
            api_key: API key for LLM backend (uses env var LLM_API_KEY if None).
            api_base: API base URL (uses env var LLM_API_BASE or default if None).
            model: Model name (uses env var LLM_MODEL or default if None).
        """
        super().__init__(backend=backend)
        if examples_dir is None:
            examples_dir = Path(__file__).resolve().parent.parent / "examples" / "scene_graphs"
        self.examples_dir = Path(examples_dir)

        # Initialize LLM client for non-mock mode
        if not self.is_mock:
            self.llm = LLMClient(api_base=api_base, api_key=api_key, model=model)
        else:
            self.llm = None

    def plan(self, user_prompt: str) -> SceneGraph:
        """Generate a scene graph from a user prompt.

        Args:
            user_prompt: Natural language description of the desired scene.

        Returns:
            A SceneGraph instance.

        Raises:
            FileNotFoundError: In mock mode, if no matching example is found.
            RuntimeError: In LLM mode, if the API call fails.
        """
        if self.is_mock:
            return self._plan_mock(user_prompt)
        else:
            return self._plan_openai(user_prompt)

    def _plan_mock(self, user_prompt: str) -> SceneGraph:
        """Mock planner: select scene graph by keyword matching.

        Searches the prompt (lowercased) for known keywords and loads the
        corresponding example JSON file.

        Args:
            user_prompt: The user's natural language prompt.

        Returns:
            A SceneGraph loaded from the matching example file.

        Raises:
            FileNotFoundError: If no keyword matches or the example file is missing.
        """
        prompt_lower = user_prompt.lower()

        matched_scene = None
        for keyword, filename in KEYWORD_TO_SCENE.items():
            if keyword in prompt_lower:
                matched_scene = filename
                logger.info("Planner matched keyword '%s' -> %s", keyword, filename)
                break

        if matched_scene is None:
            logger.warning(
                "No keyword matched in prompt. Falling back to generic_room. "
                "Prompt: '%s'",
                user_prompt,
            )
            matched_scene = "cyberpunk_bedroom.json"

        filepath = self.examples_dir / matched_scene
        if not filepath.exists():
            raise FileNotFoundError(
                f"Example scene graph not found: {filepath}\n"
                f"Keyword matched: {matched_scene}"
            )

        data = load_json(filepath)
        scene_graph = SceneGraph(**data)

        scene_graph = self._expand_mock_scene_from_prompt(scene_graph, user_prompt)

        # Update metadata with the actual source prompt
        scene_graph.metadata["source_prompt"] = user_prompt
        scene_graph.metadata["planner_backend"] = "mock"
        scene_graph.metadata["mock_strategy"] = "keyword_base_plus_prompt_expansion"

        logger.info(
            "Planner loaded scene graph: %s | objects=%d | relations=%d",
            scene_graph.scene_id,
            len(scene_graph.objects),
            len(scene_graph.relations),
        )
        return scene_graph

    def _expand_mock_scene_from_prompt(self, scene_graph: SceneGraph, user_prompt: str) -> SceneGraph:
        """Add prompt-requested supported objects to the selected mock scene.

        The mock backend remains deterministic, but it now reacts to object words
        and common synonyms in the prompt instead of returning only five fixed
        fixtures. This keeps offline demos useful for complex prompts.
        """
        prompt_lower = user_prompt.lower()
        desired_types = self._extract_desired_object_types(prompt_lower)
        if not desired_types:
            return scene_graph

        graph = scene_graph.model_copy(deep=True)
        self._adapt_scene_type_and_style(graph, prompt_lower)

        existing_types = {obj.type for obj in graph.objects}
        existing_ids = {obj.id for obj in graph.objects}
        next_index = self._next_object_index(graph)

        for obj_type in sorted(desired_types):
            if obj_type in existing_types:
                continue
            obj_id = f"{obj_type}_{next_index.get(obj_type, 0) + 1}"
            next_index[obj_type] = next_index.get(obj_type, 0) + 1
            while obj_id in existing_ids:
                next_index[obj_type] += 1
                obj_id = f"{obj_type}_{next_index[obj_type]}"

            obj = self._make_prompt_object(obj_type, obj_id, graph, prompt_lower)
            graph.objects.append(obj)
            existing_ids.add(obj_id)
            existing_types.add(obj_type)

            rel = self._make_default_relation(obj, graph, prompt_lower)
            if rel is not None:
                graph.relations.append(rel)

        if len(graph.objects) >= 10:
            graph.room.width = max(graph.room.width, 7.0)
            graph.room.depth = max(graph.room.depth, 6.0)

        graph.scene_id = re.sub(r"[^a-z0-9_]+", "_", graph.scene_id.lower()).strip("_")
        return graph

    def _extract_desired_object_types(self, prompt_lower: str) -> set[str]:
        desired: set[str] = set()
        for obj_type, patterns in PROMPT_OBJECT_PATTERNS.items():
            for pattern in patterns:
                if re.search(r"\b" + re.escape(pattern) + r"s?\b", prompt_lower):
                    desired.add(obj_type)
                    break

        # Some supported stand-ins are needed for unsupported prompt nouns.
        if "tv stand" in prompt_lower:
            desired.update({"table", "monitor"})
        if "floor cushion" in prompt_lower or "tea room" in prompt_lower:
            desired.update({"chair", "sofa"})
        if "crystal ball" in prompt_lower or "floating" in prompt_lower:
            desired.update({"glowing_tube", "neon_light"})
        if "study room" in prompt_lower:
            desired.add("plant")
        if "classroom" in prompt_lower:
            desired.add("bookshelf")
        return desired

    def _adapt_scene_type_and_style(self, graph: SceneGraph, prompt_lower: str) -> None:
        if "classroom" in prompt_lower:
            graph.scene_type = "classroom"
        elif "coffee" in prompt_lower:
            graph.scene_type = "coffee_shop"
        elif "laboratory" in prompt_lower or "medical" in prompt_lower or "sci-fi" in prompt_lower:
            graph.scene_type = "laboratory"
        elif "bedroom" in prompt_lower or "gamer room" in prompt_lower:
            graph.scene_type = "bedroom"
        elif "study" in prompt_lower:
            graph.scene_type = "study_room"
        elif any(term in prompt_lower for term in ("living room", "artist studio", "tea room")):
            graph.scene_type = "generic_room"

        style = {s.lower() for s in graph.style}
        for keyword in STYLE_KEYWORDS:
            if keyword in prompt_lower:
                style.add(keyword.replace(" ", "-"))
        graph.style = sorted(style)

        if any(term in prompt_lower for term in ("neon", "glowing", "magical", "cyberpunk")):
            graph.lighting.use_emissive_lights = True
            if "blue" in prompt_lower and "blue" not in graph.lighting.main_colors:
                graph.lighting.main_colors.append("blue")
            if "magenta" in prompt_lower and "magenta" not in graph.lighting.main_colors:
                graph.lighting.main_colors.append("magenta")
        if "warm" in prompt_lower:
            graph.lighting.mood = "warm and cozy"
            if "warm yellow" not in graph.lighting.main_colors:
                graph.lighting.main_colors.append("warm yellow")

    @staticmethod
    def _next_object_index(graph: SceneGraph) -> dict[str, int]:
        indexes: dict[str, int] = {}
        for obj in graph.objects:
            match = re.search(r"_(\d+)$", obj.id)
            idx = int(match.group(1)) if match else 1
            indexes[obj.type] = max(indexes.get(obj.type, 0), idx)
        return indexes

    def _make_prompt_object(
        self, obj_type: str, obj_id: str, graph: SceneGraph, prompt_lower: str
    ) -> SceneObject:
        defaults = OBJECT_DEFAULTS[obj_type]
        semantic_position = str(defaults["position"])
        if obj_type in WALL_OBJECT_TYPES:
            semantic_position = self._wall_position_for_prompt(obj_type, prompt_lower)
        elif obj_type in ON_OBJECT_TYPES:
            support_id = self._find_support_object_id(graph, preferred_for=obj_type) or "table_1"
            semantic_position = f"on {support_id}"
        elif obj_type == "plant" and "front-right" in prompt_lower:
            semantic_position = "front-right corner"
        elif obj_type == "bookshelf" and "back-right" in prompt_lower:
            semantic_position = "back-right corner"

        return SceneObject(
            id=obj_id,
            type=obj_type,
            description=f"prompt-requested {obj_type.replace('_', ' ')}",
            semantic_position=semantic_position,
            size=list(defaults["size"]),
            material=str(defaults["material"]),
            color=str(defaults["color"]),
            rotation=[0, 0, 0],
            extra={},
        )

    @staticmethod
    def _wall_position_for_prompt(obj_type: str, prompt_lower: str) -> str:
        if "left wall" in prompt_lower:
            return "left wall"
        if "right wall" in prompt_lower:
            return "right wall"
        if "front wall" in prompt_lower:
            return "front wall"
        if "back wall" in prompt_lower:
            return "back wall"
        if obj_type == "window" and "right" in prompt_lower:
            return "right wall"
        return str(OBJECT_DEFAULTS[obj_type]["position"])

    @staticmethod
    def _find_support_object_id(graph: SceneGraph, preferred_for: str) -> str | None:
        support_order = ["desk", "table", "counter", "shelf", "bookshelf"]
        if preferred_for == "cup":
            support_order = ["table", "desk", "counter", "shelf"]
        for support_type in support_order:
            for obj in graph.objects:
                if obj.type == support_type:
                    return obj.id
        return None

    def _make_default_relation(
        self, obj: SceneObject, graph: SceneGraph, prompt_lower: str
    ) -> Relation | None:
        if obj.type in WALL_OBJECT_TYPES:
            wall = self._wall_position_for_prompt(obj.type, prompt_lower).replace(" ", "_")
            return Relation(subject=obj.id, predicate="attached_to", object=wall)
        if obj.type in ON_OBJECT_TYPES:
            support_id = obj.semantic_position.replace("on ", "", 1).strip()
            if any(existing.id == support_id for existing in graph.objects):
                return Relation(subject=obj.id, predicate="on", object=support_id)
            return None
        if obj.type == "chair":
            support_id = self._find_support_object_id(graph, preferred_for="chair")
            if support_id:
                return Relation(subject=obj.id, predicate="in_front_of", object=support_id)
        if obj.type == "carpet":
            support_id = self._find_support_object_id(graph, preferred_for="carpet")
            if support_id:
                return Relation(subject=obj.id, predicate="near", object=support_id)
        return None

    def _plan_openai(self, user_prompt: str) -> SceneGraph:
        """LLM-based planner: generate a novel scene graph from any prompt.

        Uses the configured LLM (Google AI Studio by default) to convert
        a natural language prompt into a structured SceneGraph JSON.

        Args:
            user_prompt: The user's natural language prompt.

        Returns:
            A SceneGraph instance generated by the LLM.

        Raises:
            RuntimeError: If the LLM call fails or returns invalid data.
        """
        if self.llm is None:
            raise RuntimeError("LLM client not initialized. Use backend='openai_compatible'.")

        logger.info("Planner: calling LLM to generate scene graph...")

        # Add supported types and schema to the user prompt for context
        full_user_prompt = (
            f"Generate a complete 3D scene graph JSON for the following description.\n\n"
            f"USER REQUEST: {user_prompt}\n\n"
            f"Remember: Output ONLY valid JSON. No markdown, no backticks, no extra text."
        )

        try:
            raw_json = self.llm.chat_json(
                system_prompt=PLANNER_SYSTEM_PROMPT,
                user_prompt=full_user_prompt,
                temperature=0.3,  # Low temperature for more deterministic output
            )
        except Exception as e:
            raise RuntimeError(
                f"LLM planner failed to generate scene graph: {e}"
            ) from e

        # Validate and coerce the LLM output into a SceneGraph
        try:
            scene_graph = SceneGraph(**raw_json)
        except Exception as e:
            # Log the raw response for debugging
            logger.error("LLM output failed Pydantic validation: %s", e)
            logger.error("Raw LLM output (first 2000 chars): %s", json.dumps(raw_json)[:2000])
            raise RuntimeError(
                f"LLM output does not match SceneGraph schema: {e}\n"
                f"Raw output saved in logs."
            ) from e

        # Update metadata
        scene_graph.metadata["source_prompt"] = user_prompt
        scene_graph.metadata["planner_backend"] = "openai_compatible"
        scene_graph.metadata["llm_model"] = self.llm.model

        logger.info(
            "Planner generated scene: %s | objects=%d | relations=%d | type=%s",
            scene_graph.scene_id,
            len(scene_graph.objects),
            len(scene_graph.relations),
            scene_graph.scene_type,
        )
        return scene_graph
