# -*- coding: utf-8 -*-
"""
Antigravity Service Management Script

Usage:
    python manage.py start    - Start the service
    python manage.py stop     - Stop the service (kills process on port 8080)
    python manage.py restart  - Restart the service
    python manage.py status   - Check service status
"""
import sys
import time
import subprocess
import argparse
import psutil
import os
from typing import Optional

PORT = 8080
MAIN_SCRIPT = "main.py"

def get_process_on_port(port: int) -> Optional[psutil.Process]:
    """Find the process ID listening on the specified port"""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            for con in proc.connections():
                if con.laddr.port == port and con.status == 'LISTEN':
                    return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return None

def start_service():
    """Start the service"""
    existing_proc = get_process_on_port(PORT)
    if existing_proc:
        print(f"Service is already running! (PID: {existing_proc.pid})")
        return

    print("Starting Antigravity Service...")
    
    # Run in separate window or background depending on OS?
    # For simplicity, we just run it using subprocess in current environment
    # But since we want "service" behavior, we might want Popen without waiting
    
    # Get the directory of the current script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    cmd = [sys.executable, MAIN_SCRIPT]
    if os.name == 'nt':
        # Windows: Use creationflags to detach? Or just run.
        # If we use start_new_session, it won't die when this script dies
        # CREATE_NEW_CONSOLE to open in new window
        subprocess.Popen(cmd, cwd=script_dir, creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        subprocess.Popen(cmd, cwd=script_dir, start_new_session=True)
        
    print("Service started in a new window/process.")
    print("   Waiting for port binding...")
    
    # Wait for port to be active
    for _ in range(20):
        time.sleep(1)
        if get_process_on_port(PORT):
            print(f"Service is UP and LISTENING on port {PORT}")
            return
            
    print("Service started but port 8080 is not yet active. Please check the new window for errors.")

def stop_service():
    """Stop the service completely"""
    print(f"Stopping service on port {PORT}...")
    
    count = 0
    # Kill process on port
    proc = get_process_on_port(PORT)
    if proc:
        print(f"   Found Check: PID {proc.pid} ({proc.name()})")
        try:
            # Kill children first
            children = proc.children(recursive=True)
            for child in children:
                child.kill()
            proc.kill()
            proc.wait(timeout=5)
            print("   Process terminated.")
            count += 1
        except Exception as e:
            print(f"   Error killing process: {e}")
    else:
        print("   No process found listening on port 8080.")

    # Double check for python processes running main.py (in case port wasn't bound yet)
    # This acts as a cleanup for zombies that might not be listening
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.cmdline()
            if cmdline and len(cmdline) >= 2 and MAIN_SCRIPT in cmdline[-1]:
                print(f"   Cleaning up potential zombie: PID {proc.pid}")
                proc.kill()
                count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
            
    if count > 0:
        print(f"Stopped {count} process(es).")
    else:
        print("Service was not running.")

def check_status():
    """Check service status"""
    proc = get_process_on_port(PORT)
    if proc:
        print(f"Service is RUNNING (PID: {proc.pid})")
        print(f"   Host: http://localhost:{PORT}")
    else:
        print("Service is STOPPED")

def main():
    parser = argparse.ArgumentParser(description="Manage Antigravity Service")
    parser.add_argument("action", choices=["start", "stop", "restart", "status"], help="Action to perform")
    
    args = parser.parse_args()
    
    if args.action == "start":
        start_service()
    elif args.action == "stop":
        stop_service()
    elif args.action == "restart":
        stop_service()
        time.sleep(2) # Give OS time to release port
        start_service()
    elif args.action == "status":
        check_status()

if __name__ == "__main__":
    main()
