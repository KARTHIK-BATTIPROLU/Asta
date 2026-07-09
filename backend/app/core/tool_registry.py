import os
import glob
import importlib
import logging
from typing import Dict, Any, Callable, Type
from pydantic import BaseModel

logger = logging.getLogger("ToolRegistry")

class ToolDef:
    def __init__(self, name: str, description: str, schema: Type[BaseModel], handler: Callable):
        self.name = name
        self.description = description
        self.schema = schema
        self.handler = handler

    def spec_openai(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.schema.model_json_schema()
            }
        }

    def spec_mcp(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.schema.model_json_schema()
        }

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolDef] = {}

    def register(self, tool_def: ToolDef):
        self._tools[tool_def.name] = tool_def

    def get_tool(self, name: str) -> ToolDef:
        return self._tools.get(name)

    def get_all_openai_specs(self) -> list:
        return [t.spec_openai() for t in self._tools.values()]

    def get_all_mcp_specs(self) -> list:
        return [t.spec_mcp() for t in self._tools.values()]

    def auto_discover(self, tools_dir: str = "backend/app/tools"):
        """Scans the tools/ directory and loads all tool definitions."""
        if not os.path.exists(tools_dir):
            return
            
        # Simplified auto-discovery: load modules and look for 'TOOL_DEF'
        # Convert path to module format
        base_module = tools_dir.replace("/", ".").replace("\\", ".")
        
        for file in glob.glob(os.path.join(tools_dir, "*.py")):
            basename = os.path.basename(file)
            if basename.startswith("__"):
                continue
                
            module_name = basename[:-3]
            try:
                mod = importlib.import_module(f"{base_module}.{module_name}")
                if hasattr(mod, "TOOL_DEF"):
                    self.register(mod.TOOL_DEF)
                    logger.info(f"Registered tool: {mod.TOOL_DEF.name}")
            except Exception as e:
                logger.error(f"Failed to load tool from {basename}: {e}")

# Global registry singleton
registry = ToolRegistry()
