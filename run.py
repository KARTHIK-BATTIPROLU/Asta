import sys, asyncio, os, subprocess

def kill_process_on_port(port):
    try:
        if sys.platform == 'win32':
            result = subprocess.check_output(f'netstat -ano | findstr :{port}', shell=True).decode()
            for line in result.splitlines():
                if 'LISTENING' in line:
                    pid = line.strip().split()[-1]
                    os.system(f'taskkill /F /PID {pid}')
                    print(f'Killed process {pid} on port {port}')
    except Exception as e:
        pass

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
import uvicorn
if __name__ == '__main__':
    kill_process_on_port(8000)
    uvicorn.run('backend.app.main:app', host='0.0.0.0', port=8000, reload=False)
