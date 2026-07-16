import logging
import json
import time
import uuid
import hmac
import hashlib
import httpx
from typing import List, Dict, Any
from backend.app.core.llm_factory import router
from backend.app.config import settings
import os

logger = logging.getLogger(__name__)

class DevAgentService:
    def __init__(self):
        # We assume gateway is running locally for phase 8 dev testing
        self.gateway_url = "http://localhost:8888/execute"
        self.secret = os.getenv("GATEWAY_HMAC_SECRET", "default_dev_secret").encode("utf-8")
        
    def _sign_payload(self, payload: dict) -> dict:
        canonical = json.dumps(payload, separators=(',', ':'), sort_keys=True)
        sig = hmac.new(self.secret, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        payload["hmac"] = sig
        return payload

    async def _dispatch_to_gateway(self, payload: dict) -> dict:
        signed_payload = self._sign_payload(payload)
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(self.gateway_url, json=signed_payload)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error(f"[DevAgent] Gateway dispatch failed: {e}")
            return {"exit_code": -1, "stdout": "", "stderr": str(e)}

    async def execute_task(self, project_dir: str, goal: str, caps: dict = None) -> str:
        """
        Orchestrates a development task.
        caps: {"wall": 90, "loops": 25, "groq_calls": 60}
        """
        logger.info(f"[DevAgent] Starting task '{goal}' in {project_dir}")
        caps = caps or {"wall": 90, "loops": 25, "groq_calls": 60}
        
        task_id = str(uuid.uuid4())[:8]
        branch_name = f"asta/{task_id}"
        
        # 1. Initialize Git & Branch
        init_res = await self.run_command(["git", "init"], cwd=project_dir)
        branch_res = await self.run_command(["git", "checkout", "-b", branch_name], cwd=project_dir)
        if branch_res["exit_code"] != 0 and "fatal: not a git repository" not in branch_res["stderr"]:
             # Try creating if it didn't exist
             await self.run_command(["git", "checkout", "-b", branch_name], cwd=project_dir)
             
        logger.info(f"[DevAgent] Branch {branch_name} created.")

        # 2. Planning
        plan_prompt = f"Decompose this task into 3 terminal commands or actions. Task: {goal}. Respond ONLY with the commands, one per line."
        plan_res = await router.run("coding_brain", [{"role": "user", "content": plan_prompt}])
        
        commands = [cmd.strip() for cmd in plan_res.text.split("\n") if cmd.strip() and not cmd.startswith("#")]
        
        # 3. Execution Loop
        results = []
        for i, cmd_str in enumerate(commands[:caps.get("loops", 5)]):
            logger.info(f"[DevAgent] Executing step {i+1}: {cmd_str}")
            # Simplified parser for argv
            argv = cmd_str.split(" ")
            
            res = await self.run_command(argv, cwd=project_dir)
            results.append(f"$ {cmd_str}\nExit: {res['exit_code']}\nOut: {res['stdout']}\nErr: {res['stderr']}")
            
            # Simulated Milestone Commit
            await self.run_command(["git", "add", "."], cwd=project_dir)
            await self.run_command(["git", "commit", "-m", f"Step {i+1}: {cmd_str[:20]}"], cwd=project_dir)

        # 4. Final Review
        summary = "\n".join(results)
        logger.info(f"[DevAgent] Task complete. Summary length: {len(summary)}")
        return f"Boss, task is done on branch {branch_name}."

    async def run_command(self, argv: List[str], cwd: str, timeout_s: int = 60) -> dict:
        payload = {
            "v": 2,
            "id": str(uuid.uuid4()),
            "ts": int(time.time()),
            "nonce": str(uuid.uuid4()),
            "cmd": "exec",
            "argv": argv,
            "cwd": cwd,
            "timeout_s": timeout_s
        }
        return await self._dispatch_to_gateway(payload)

dev_agent_service = DevAgentService()
