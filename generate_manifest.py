import os
import subprocess

def get_last_commit(filepath):
    try:
        out = subprocess.check_output(['git', 'log', '-1', '--format=%h', '--', filepath]).decode().strip()
        return out if out else 'Unknown'
    except:
        return 'Error'

def process_dir(start_path):
    print('| File Path | Purpose | Last Commit | Imported By | Tag |')
    print('|---|---|---|---|---|')
    for root, dirs, files in os.walk(start_path):
        if 'node_modules' in root or '.venv' in root or '__pycache__' in root or '.git' in root:
            continue
        for file in files:
            if not file.endswith(('.py', '.yml', '.md', '.sh')): continue
            filepath = os.path.join(root, file).replace('\\\\', '/')
            relpath = os.path.relpath(filepath, start_path).replace('\\\\', '/')
            commit = get_last_commit(relpath)
            
            tag = 'UNCLEAR'
            if 'hermes' in relpath: tag = 'KEEP-HERMES'
            elif 'memory' in relpath: tag = 'KEEP-MEMORY-LAYER'
            elif 'api' in relpath and 'content' not in relpath: tag = 'KEEP-MESSAGE-LAYER'
            elif 'content' in relpath: tag = 'UNRELATED-FEATURE'
            
            print(f'| {relpath} | TBD | {commit} | TBD | {tag} |')

process_dir('.')
