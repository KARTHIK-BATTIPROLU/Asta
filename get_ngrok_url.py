#!/usr/bin/env python3
"""
Script to dynamically fetch the current ngrok public URL
"""
import requests
import json
import sys

def get_ngrok_url():
    """
    Fetch the current ngrok public URL from the local ngrok API
    """
    try:
        # ngrok exposes a local API at http://127.0.0.1:4040/api/tunnels
        response = requests.get('http://127.0.0.1:4040/api/tunnels', timeout=5)
        response.raise_for_status()
        
        data = response.json()
        tunnels = data.get('tunnels', [])
        
        if not tunnels:
            print("ERROR: No active ngrok tunnels found", file=sys.stderr)
            return None
        
        # Find the HTTPS tunnel
        for tunnel in tunnels:
            if tunnel.get('proto') == 'https':
                public_url = tunnel.get('public_url')
                if public_url:
                    # Ensure it ends with /
                    if not public_url.endswith('/'):
                        public_url += '/'
                    return public_url
        
        # Fallback to first tunnel if no HTTPS found
        public_url = tunnels[0].get('public_url', '')
        if not public_url.endswith('/'):
            public_url += '/'
        return public_url
        
    except requests.exceptions.ConnectionError:
        print("ERROR: Cannot connect to ngrok API. Is ngrok running?", file=sys.stderr)
        return None
    except requests.exceptions.Timeout:
        print("ERROR: Timeout connecting to ngrok API", file=sys.stderr)
        return None
    except Exception as e:
        print(f"ERROR: {str(e)}", file=sys.stderr)
        return None

def update_android_config(ngrok_url):
    """
    Update the Android app's network configuration with the new ngrok URL
    """
    config_file = "ASTA MOBILE/app/src/main/java/com/example/asta/network/AstaNetworkClient.kt"
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find and replace the BASE_URL line
        lines = content.split('\n')
        updated_lines = []
        
        for line in lines:
            if 'val BASE_URL = ' in line and 'ngrok' in line:
                # Replace with new URL
                indent = len(line) - len(line.lstrip())
                updated_lines.append(' ' * indent + f'val BASE_URL = "{ngrok_url}"')
            else:
                updated_lines.append(line)
        
        updated_content = '\n'.join(updated_lines)
        
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        
        print(f"✓ Updated Android config with URL: {ngrok_url}")
        return True
        
    except Exception as e:
        print(f"ERROR updating Android config: {str(e)}", file=sys.stderr)
        return False

if __name__ == '__main__':
    print("Fetching ngrok URL...")
    url = get_ngrok_url()
    
    if url:
        print(f"✓ Found ngrok URL: {url}")
        
        # Update Android config
        if update_android_config(url):
            print("\n✓ Android app is now configured with the current ngrok URL")
            print("  You can now build and run the Android app")
        else:
            print("\n✗ Failed to update Android config")
            sys.exit(1)
    else:
        print("\n✗ Failed to get ngrok URL")
        print("  Make sure ngrok is running with: ngrok http 8000")
        sys.exit(1)
