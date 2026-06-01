import asyncio
import json
import logging
import os
import signal
from typing import Optional

try:
    import websockets
except ImportError:
    print("Install websockets to run OpenClaw gateway: pip install websockets")
    exit(1)

logging.basicConfig(level=logging.INFO, format="[OpenClaw Gateway] %(levelname)s - %(message)s")

class OpenClawGateway:
    """
    Local daemon that securely bridges WebSocket commands from ASTA 
    to native shell processes using subprocess.exec (shell=False).
    """
    def __init__(self, host="127.0.0.1", port=8888):
        self.host = host
        self.port = port
        self.active_processes = set()

    async def _stream_reader(self, reader: asyncio.StreamReader, ws: websockets.WebSocketServerProtocol, stream_type: str):
        """Asynchronously reads from stdout/stderr and streams back via WebSocket."""
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                decoded_line = line.decode('utf-8', errors='replace').rstrip('\n\r')
                if decoded_line:
                    await ws.send(json.dumps({"type": stream_type, "data": decoded_line}))
        except Exception as e:
            logging.error(f"Error streaming {stream_type}: {e}")

    async def handler(self, ws: websockets.WebSocketServerProtocol, path: str):
        """Handles incoming WebSocket connections."""
        client_ip = ws.remote_address[0]
        if client_ip != "127.0.0.1":
            logging.warning(f"Rejected connection from non-local IP: {client_ip}")
            await ws.close(code=1008, reason="Only localhost allowed")
            return
            
        logging.info(f"Client connected from {client_ip}")
        process: Optional[asyncio.subprocess.Process] = None

        try:
            async for message in ws:
                payload = json.loads(message)
                argv = payload.get("argv")
                
                # Validation
                if not argv or not isinstance(argv, list) or len(argv) == 0:
                    await ws.send(json.dumps({"type": "error", "data": "Invalid payload. 'argv' array required."}))
                    break

                binary = argv[0]
                logging.info(f"Executing: {' '.join(argv)}")

                # Execute strictly without shell injection vulnerabilities
                try:
                    process = await asyncio.create_subprocess_exec(
                        *argv,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env=os.environ.copy()
                    )
                    self.active_processes.add(process)

                    # Gather streams concurrently
                    await asyncio.gather(
                        self._stream_reader(process.stdout, ws, "stdout"),
                        self._stream_reader(process.stderr, ws, "stderr"),
                    )

                    await process.wait()
                    
                    if process in self.active_processes:
                        self.active_processes.remove(process)

                    await ws.send(json.dumps({"type": "completed", "data": f"Exit code: {process.returncode}"}))

                except FileNotFoundError:
                    logging.error(f"Binary not found: {binary}")
                    await ws.send(json.dumps({"type": "error", "data": f"Binary not found: {binary}"}))
                except Exception as e:
                    logging.error(f"Execution failed: {e}")
                    await ws.send(json.dumps({"type": "error", "data": f"Execution failed: {str(e)}"}))
                
                break  # Close after one execution per connection
                
        except websockets.exceptions.ConnectionClosed:
            logging.info("WebSocket connection closed by client.")
        except Exception as e:
            logging.error(f"Handler error: {e}")
        finally:
            # Cleanup any dangling processes
            if process and process.returncode is None:
                logging.info("Terminating orphaned process.")
                try:
                    process.terminate()
                except Exception:
                    pass
                if process in self.active_processes:
                    self.active_processes.remove(process)

    async def start(self):
        logging.info(f"Starting Gateway on ws://{self.host}:{self.port}")
        server = await websockets.serve(self.handler, self.host, self.port)
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    gateway = OpenClawGateway()
    try:
        asyncio.run(gateway.start())
    except KeyboardInterrupt:
        logging.info("Gateway shutting down.")