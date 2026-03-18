"""Signal handling utilities - extracted from main.py"""
import signal
import sys
import os
import traceback


def create_signal_handler():
    """Create and register signal handlers for the application."""
    
    def _signal_handler(signum, frame):
        sig_name = signal.Signals(signum).name
        print(f"[SIGNAL] Caught {sig_name}, traceback:", file=sys.stderr)
        traceback.print_stack(frame)
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGHUP, _signal_handler)
    print(f"[SIGNAL] Handlers registered, PID: {os.getpid()}", file=sys.stderr)
    
    return _signal_handler
