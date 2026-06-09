import asyncio
import time
import logging
import json
import os
import re
import websockets
from typing import Dict, Any, List

from backend.app.models.action_model import ActionRequest, ActionResult, SHELL_METACHAR_PATTERN, TARGET_SAFE_PATTERN
from backend.app.core.registry import registry
from backend.app.services.l1_cache import l1_manager
from backend.app.core.circuit_breaker import OpenClawCircuitBreaker

logger = logging.getLogger(__name__)


class WebSearchTool:
    """Mock tool simulating a web search API."""
    async def run(self, parameters: Dict[str, Any]) -> str:
        query = parameters.get("query", "")
        # Simulate network delay (modify this parameter to test timeouts > 2.0s)
        delay = parameters.get("delay", 0.5)
        await asyncio.sleep(delay)
        
        # Simulate a large response payload
        long_content = "Here is some search result text. " * 500
        return f"Search Results for '{query}': {long_content}"


class SkillsRetrieverTool:
    """Retrieves user skills and projects via Neo4j Graph."""
    async def run(self, parameters: Dict[str, Any]) -> str:
        user_name = parameters.get("name", "KARTHIK")
        try:
            db_manager = registry.get("db")
            if not db_manager or not hasattr(db_manager, "neo4j_driver"):
                return "Error: Graph DB not configured."
                
            driver = db_manager.neo4j_driver
            query = "MATCH (u:Identity {name: $name})-[:HAS_SKILL]->(s) RETURN s.name AS skill_name"
            
            async with driver.session() as session:
                result = await session.run(query, name=user_name)
                records = await result.data()
                
            skills = [r["skill_name"] for r in records if r.get("skill_name")]
            if skills:
                return f"Skills found for {user_name}: {', '.join(skills)}"
            return f"No skills defined for {user_name}."
        except Exception as e:
            logger.error(f"[SkillsRetrieverTool] Failed: {e}")
            return f"Error retrieving skills: {e}"


class OpenClawTool:
    """
    Executes native Kali Linux commands via OpenClaw Gateway WebSocket.
    
    SECURITY MODEL:
    - Tool binary is validated against a strict allowlist (OpenClawCircuitBreaker)
    - Arguments are validated per-tool against flag allowlists
    - Shell metacharacters are rejected before any command reaches the gateway
    - Commands are sent as structured argv arrays, NEVER as concatenated strings
    """
    
    # Per-tool argument validation schemas
    TOOL_ARG_SCHEMAS = {
        "nmap": {
            "allowed_flags": {
                "-sV", "-sS", "-sT", "-sU", "-sN", "-sF", "-sX",
                "-O", "-A", "-p", "-Pn", "-F", "-T0", "-T1", "-T2", "-T3", "-T4", "-T5",
                "--top-ports", "--open", "-oN", "-oX", "-oG", "-v", "-vv",
                "--script", "--version-intensity", "-n", "-R",
            },
            "requires_target": True,
            "max_args": 15,
        },
        "ping": {
            "allowed_flags": {"-c", "-W", "-i", "-t", "-n", "-4", "-6"},
            "requires_target": True,
            "max_args": 6,
        },
        "whois": {
            "allowed_flags": {"-h", "-p"},
            "requires_target": True,
            "max_args": 5,
        },
        "ls": {
            "allowed_flags": {"-l", "-a", "-la", "-lah", "-R", "-1", "-h", "-t", "-S"},
            "requires_target": False,
            "max_args": 5,
        },
        "gobuster": {
            "allowed_flags": {
                "dir", "dns", "vhost", "fuzz",
                "-u", "-w", "-t", "-o", "-q", "-x", "-s", "-b",
                "--url", "--wordlist", "--threads", "--timeout",
            },
            "requires_target": False,  # Target is passed via -u flag
            "max_args": 15,
        },
        "curl": {
            "allowed_flags": {
                "-I", "-s", "-o", "-L", "-v", "-k",
                "--max-time", "--connect-timeout", "-H", "--head",
            },
            "blocked_flags": {
                "-X", "-d", "--data", "--data-raw", "--data-binary",
                "-F", "--form", "--upload-file", "-T", "--request",
                "-O",  # No downloading to arbitrary paths
            },
            "requires_target": True,
            "max_args": 10,
        },
        "git": {
            "allowed_flags": {
                "init", "status", "log", "diff", "add", "commit", "-m", "-a",
                "branch", "checkout", "-b", "clone", "pull", "push", "remote", "-v"
            },
            "requires_target": False,
            "max_args": 15,
        },
        "mkdir": {
            "allowed_flags": {"-p", "-v"},
            "requires_target": True,
            "max_args": 5,
        },
        "python": {
            "allowed_flags": {"-c", "-V", "-m"},
            "requires_target": False,
            "max_args": 5,
        },
        "docker": {
            "allowed_flags": {
                "ps", "images", "run", "stop", "rm", "rmi", "build", "logs", "inspect", "-d", "-p", "-v", "-t", "-i", "-a", "-f"
            },
            "requires_target": False,
            "max_args": 15,
        }
    }

    @classmethod
    def validate_args(cls, tool: str, args: List[str], target: str) -> tuple:
        """
        Validate tool arguments against security schema.
        Returns: (is_safe: bool, reason: str, sanitized_argv: list)
        """
        schema = cls.TOOL_ARG_SCHEMAS.get(tool)
        if not schema:
            return False, f"No argument schema defined for tool '{tool}'", []
        
        # Validate arg count
        if len(args) > schema.get("max_args", 10):
            return False, f"Too many arguments ({len(args)} > {schema['max_args']})", []
        
        # Validate each argument
        blocked = schema.get("blocked_flags", set())
        allowed = schema.get("allowed_flags", set())
        sanitized = []
        
        for arg in args:
            arg_str = str(arg).strip()
            if not arg_str:
                continue
            
            # Check shell metacharacters (defense in depth — model also validates)
            if SHELL_METACHAR_PATTERN.search(arg_str):
                return False, f"Shell metacharacter in argument: '{arg_str}'", []
            
            # Check blocked flags
            if arg_str.startswith("-"):
                flag = arg_str.split("=")[0]
                if flag in blocked:
                    return False, f"Blocked flag: {flag}", []
                # Only validate against allowed list if the allowed set is non-empty
                if allowed and flag not in allowed:
                    # Allow non-flag values (e.g., port numbers after -p)
                    pass  # Non-flag args are allowed through
            
            sanitized.append(arg_str)
        
        # Validate target
        target_clean = target.strip() if target else ""
        if schema.get("requires_target") and not target_clean:
            return False, "Target is required for this tool but was empty", []
        
        if target_clean and not TARGET_SAFE_PATTERN.match(target_clean):
            return False, f"Invalid target format: '{target_clean}'", []
        
        # Build final argv
        argv = [tool] + sanitized
        if target_clean:
            argv.append(target_clean)
        
        return True, "", argv

    async def run(self, parameters: Dict[str, Any]) -> str:
        tool_name = parameters.get("tool", "")
        raw_args = parameters.get("args", [])
        target = parameters.get("target", "")

        if not tool_name:
            return "Error: No tool name provided in payload."

        # Step 1: Strict allowlist check on the binary name
        is_safe, reason = OpenClawCircuitBreaker.sanitize(tool_name, raw_args, target)
        if not is_safe:
            logger.error(f"[OpenClaw] Security Block: {reason}")
            return f"Security Block: {reason}. Execution aborted."
        
        # Step 2: Ensure args is a list
        if isinstance(raw_args, str):
            raw_args = raw_args.split()
        if not isinstance(raw_args, list):
            return "Error: 'args' must be a list of strings."
        
        # Step 3: Per-tool argument validation
        args_safe, args_reason, argv = self.validate_args(tool_name, raw_args, target)
        if not args_safe:
            logger.error(f"[OpenClaw] Argument validation failed: {args_reason}")
            return f"Security Block: {args_reason}. Execution aborted."

        # Step 4: Bridge configuration and connection
        ws_url = os.getenv("OPENCLAW_WS_URL", "ws://127.0.0.1:8888/ws")
        output_buffer = []
        
        try:
            logger.info(f"[OpenClaw] Connecting to gateway {ws_url} for argv: {argv}")
            async with websockets.connect(ws_url, open_timeout=5.0) as ws:
                # Send structured argv array — gateway MUST use subprocess with shell=False
                await ws.send(json.dumps({
                    "argv": argv,
                    # Backward compat: also send command string for gateways that don't support argv yet
                    "command": " ".join(argv),
                }))
                
                # Listen to streamed chunks of terminal output
                while True:
                    msg = await ws.recv()
                    payload = json.loads(msg)
                    
                    msg_type = payload.get("type", "stdout")
                    data = payload.get("data", "")
                    
                    if msg_type in ["stdout", "stderr"]:
                        if data:
                            output_buffer.append(data)
                    elif msg_type == "completed":
                        logger.info(f"[OpenClaw] Gateway completed execution.")
                        break
                    elif msg_type == "error":
                        logger.error(f"[OpenClaw] Gateway error: {data}")
                        output_buffer.append(f"ERROR: {data}")
                        break
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"[OpenClaw] Connection closed prematurely: {e}")
        except Exception as e:
            logger.error(f"[OpenClaw] Gateway connection failed: {e}")
            return f"Connection Failed: {e}"

        return "\n".join(output_buffer)


class ActionExecutor:
    """
    Dispatches Pydantic-validated tool calls, applies strict timeouts,
    truncates results, audits to MongoDB, and updates the L1.5 cache.
    
    Tool results carry intent and memory_tag for proper L2/L3 memory indexing.
    
    Routing:
      - API tools (notion, calendar, search, weather, news, image) → ToolRegistry
      - Legacy tools (WebSearch, SkillsRetriever, openclaw_exec) → direct
    """

    API_TOOLS = {"notion", "calendar", "search", "weather", "news", "image"}

    def __init__(self):
        self.tools = {
            "WebSearch": WebSearchTool(),
            "SkillsRetriever": SkillsRetrieverTool(),
            "openclaw_exec": OpenClawTool()
        }
        self.timeout_seconds = 60.0  # Accommodate slow Kali tools like nmap/gobuster
        self.max_result_length = 2000

    async def execute_action(self, request: ActionRequest) -> ActionResult:
        start_time = time.time()

        # ── Route API tools through ToolRegistry ─────────────────────────
        if request.tool_name in self.API_TOOLS:
            return await self._execute_api_tool(request, start_time)

        # ── Legacy tool path ─────────────────────────────────────────────
        tool = self.tools.get(request.tool_name)
        
        # ── Workflow Engine execution path ───────────────────────────────
        if request.tool_name == "workflow":
            return await self._execute_workflow(request, start_time)

        if not tool:
            return await self._handle_failure(request, "Tool not found", start_time)

        try:
            # 1. Execute with strict timeout
            raw_result = await asyncio.wait_for(
                tool.run(request.parameters), 
                timeout=self.timeout_seconds
            )
            
            # 2. Format and Truncate Result (<500 tokens / ~2000 chars)
            truncated_result = self._truncate_result(str(raw_result))
            status = "success"
            
        except asyncio.TimeoutError:
            truncated_result = f"Error: Tool '{request.tool_name}' timed out after {self.timeout_seconds}s."
            status = "timeout"
            logger.warning(truncated_result)
        except Exception as e:
            truncated_result = f"Error: Tool '{request.tool_name}' failed with {str(e)}"
            status = "error"
            logger.error(truncated_result)

        latency_ms = (time.time() - start_time) * 1000

        # 3. Create Result Model (carries intent + memory_tag for L2/L3)
        result_obj = ActionResult(
            session_id=request.session_id,
            tool_name=request.tool_name,
            status=status,
            result=truncated_result,
            latency_ms=latency_ms,
            intent=request.intent,
            memory_tag=request.memory_tag,
        )

        # 4. Audit to MongoDB
        await self._audit_tool_execution(result_obj)

        # 5. Update Speculative Cache Hook (L1.5 Layer)
        self._update_speculative_cache(result_obj)

        return result_obj

    async def _execute_api_tool(self, request: ActionRequest, start_time: float) -> ActionResult:
        """
        Route API tools through the ToolRegistry.
        Commits tool result to MemorySaga for persistent memory indexing.
        """
        try:
            from backend.app.tools.tool_registry import tool_registry

            # Build payload from ActionRequest
            payload = {
                "tool": request.tool_name,
                "memory_tag": request.memory_tag or "",
                "intent": request.intent or "",
                **(request.parameters or {}),
            }

            # Execute through ToolRegistry with timeout
            tool_result = await asyncio.wait_for(
                tool_registry.route(payload, session_id=request.session_id),
                timeout=self.timeout_seconds,
            )

            status = tool_result.get("status", "error")
            result_text = self._truncate_result(
                json.dumps(tool_result.get("result", {}), default=str)
            )
            latency_ms = (time.time() - start_time) * 1000

            result_obj = ActionResult(
                session_id=request.session_id,
                tool_name=request.tool_name,
                status=status,
                result=result_text,
                latency_ms=latency_ms,
                intent=request.intent,
                memory_tag=request.memory_tag,
            )

            # Audit + L1.5 cache
            await self._audit_tool_execution(result_obj)
            self._update_speculative_cache(result_obj)

            # Commit to memory via MemorySaga (non-blocking)
            if status == "success":
                try:
                    from memory.memory_saga import MemorySaga
                    from backend.app.core.task_registry import TaskRegistry

                    summary = f"[Tool:{request.tool_name}] {request.intent or 'tool execution'} — {status}"
                    embedding_service = registry.get("embedding")
                    embedding = []
                    if embedding_service:
                        embed_text = f"{request.intent} {result_text[:500]}"
                        embedding = await asyncio.to_thread(embedding_service.embed, embed_text)

                    saga = MemorySaga(
                        session_id=request.session_id,
                        summary=summary,
                        embedding=embedding or [],
                        raw_segment=result_text[:1000],
                        source=f"tool:{request.tool_name}",
                    )
                    TaskRegistry.track(
                        saga.execute(),
                        name=f"tool_memory_commit:{request.tool_name}",
                        session_id=request.session_id,
                    )
                except Exception as mem_err:
                    logger.warning(f"[ActionExecutor] Memory commit failed (non-blocking): {mem_err}")

            return result_obj

        except asyncio.TimeoutError:
            latency_ms = (time.time() - start_time) * 1000
            result_obj = ActionResult(
                session_id=request.session_id,
                tool_name=request.tool_name,
                status="timeout",
                result=f"Tool '{request.tool_name}' timed out after {self.timeout_seconds}s",
                latency_ms=latency_ms,
                intent=request.intent,
                memory_tag=request.memory_tag,
            )
            await self._audit_tool_execution(result_obj)
            return result_obj

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"[ActionExecutor] API tool '{request.tool_name}' failed: {e}", exc_info=True)
            result_obj = ActionResult(
                session_id=request.session_id,
                tool_name=request.tool_name,
                status="error",
                result=f"Tool '{request.tool_name}' failed: {e}",
                latency_ms=latency_ms,
                intent=request.intent,
                memory_tag=request.memory_tag,
            )
            await self._audit_tool_execution(result_obj)
            return result_obj

    def _truncate_result(self, text: str) -> str:
        """Limits string to prevent massive prompts breaking token limits."""
        if len(text) > self.max_result_length:
            return text[:self.max_result_length] + "... [TRUNCATED]"
        return text

    async def _audit_tool_execution(self, result: ActionResult):
        """Logs the tool execution outcome to MongoDB collection 'tool_audits'."""
        try:
            db_manager = registry.get("db")
            if db_manager and hasattr(db_manager, "get_collection"):
                collection = db_manager.get_collection("tool_audits")
                if collection is not None:
                    import datetime
                    
                    async def do_insert():
                        doc = {
                            "session_id": result.session_id,
                            "tool_name": result.tool_name,
                            "status": result.status,
                            "latency_ms": result.latency_ms,
                            "result_preview": result.result[:500], # Keep DB footprint small
                            "intent": result.intent,
                            "memory_tag": result.memory_tag,
                            "timestamp": datetime.datetime.now(datetime.timezone.utc)
                        }
                        # If using PyMongo synchronously:
                        if hasattr(collection, "insert_one"):
                            collection.insert_one(doc)

                    # Offload to thread to ensure we don't block event loop if using sync mongodb
                    await asyncio.to_thread(do_insert)
        except Exception as e:
            logger.error(f"[ActionExecutor] Failed to audit tool execution: {e}")

    def _update_speculative_cache(self, result: ActionResult):
        """Injects the tool result into the L1.5 Speculative Cache."""
        try:
            session = l1_manager.get_session(result.session_id)
            if session:
                session.set_speculative_data(f"tool_result_{result.tool_name}", {
                    "tool": result.tool_name,
                    "status": result.status,
                    "data": result.result,
                    "intent": result.intent,
                    "memory_tag": result.memory_tag,
                })
                logger.info(f"[ActionExecutor] L1.5 cache updated with result from {result.tool_name}")
        except Exception as e:
            logger.warning(f"[ActionExecutor] Failed to update L1.5 speculative cache: {e}")

    async def _execute_workflow(self, request: ActionRequest, start_time: float) -> ActionResult:
        """Routes execution to specialized multi-step engine classes."""
        try:
            engine_name = request.parameters.get("engine")
            args = request.parameters.get("args", {})
            
            result_text = ""
            if engine_name == "routine":
                from backend.app.workflows.routine_engine import RoutineEngine
                # Check for city in args, default to Bangalore or similar if not found
                user_city = args.get("city", "Bangalore") 
                result_text = await RoutineEngine().run_morning_routine(user_city, request.session_id)
            elif engine_name == "research":
                from backend.app.workflows.research_engine import ResearchEngine
                query = args.get("query", "current events")
                result_text = await ResearchEngine().conduct_research(query, request.session_id, depth="thorough")
            elif engine_name == "content":
                from backend.app.workflows.content_engine import ContentEngine
                topic = args.get("topic", "")
                platform = args.get("platform", "linkedin")
                result_text = await ContentEngine().generate_post(topic, platform, request.session_id)
            elif engine_name == "youtube":
                from backend.app.workflows.youtube_engine import YouTubeEngine
                topic = args.get("topic", "")
                result_text = await YouTubeEngine().generate_script(topic, request.session_id)
            elif engine_name == "developer":
                # Developer engine removed during cleanup; not part of the current scope.
                return await self._handle_failure(request, "Developer workflow is not available", start_time)
            else:
                return await self._handle_failure(request, f"Unknown workflow engine: {engine_name}", start_time)

            truncated_result = self._truncate_result(result_text)
            latency_ms = (time.time() - start_time) * 1000

            result_obj = ActionResult(
                session_id=request.session_id,
                tool_name=f"workflow:{engine_name}",
                status="success",
                result=truncated_result,
                latency_ms=latency_ms,
                intent=request.intent,
                memory_tag=request.memory_tag,
            )

            await self._audit_tool_execution(result_obj)
            self._update_speculative_cache(result_obj)
            return result_obj

        except Exception as e:
            logger.error(f"[ActionExecutor] Workflow execution failed: {e}")
            return await self._handle_failure(request, f"Workflow failed: {str(e)}", start_time)

    async def _handle_failure(self, request: ActionRequest, message: str, start_time: float) -> ActionResult:
        latency_ms = (time.time() - start_time) * 1000
        result_obj = ActionResult(
            session_id=request.session_id,
            tool_name=request.tool_name,
            status="not_found",
            result=message,
            latency_ms=latency_ms,
            intent=request.intent,
            memory_tag=request.memory_tag,
        )
        await self._audit_tool_execution(result_obj)
        self._update_speculative_cache(result_obj)
        return result_obj

# Global singleton
action_executor = ActionExecutor()
