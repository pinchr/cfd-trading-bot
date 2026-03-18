"""
Optimizer Cron - Scheduler for Auto Backtest Optimizer

Runs:
- Every 10 minutes: Optimization cycle (test 5 combinations)
- Every 1 hour: Summary cycle (compare and promote winners)
"""

import asyncio
import os
import sys
import time
import signal
from datetime import datetime
from pathlib import Path

# Add backend to path
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from services.backtest_optimizer import run_cycle, run_summary, get_optimizer


# Configuration
OPTIMIZATION_INTERVAL = 600  # 10 minutes in seconds
SUMMARY_INTERVAL = 3600       # 1 hour in seconds


class OptimizerCron:
    """Cron scheduler for optimizer."""
    
    def __init__(self):
        self.running = True
        self.last_optimization = None
        self.last_summary = None
        self.cycle_count = 0
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)
    
    def _shutdown(self, signum, frame):
        """Handle shutdown gracefully."""
        print(f"[CRON] Received signal {signum}, shutting down...")
        self.running = False
    
    async def run_optimization(self):
        """Run optimization cycle."""
        print(f"[CRON] [{datetime.now().strftime('%H:%M:%S')}] Running optimization cycle #{self.cycle_count + 1}...")
        try:
            await run_cycle()
            self.last_optimization = datetime.now()
            self.cycle_count += 1
        except Exception as e:
            print(f"[CRON] Optimization failed: {e}")
    
    async def run_summary(self):
        """Run summary cycle."""
        print(f"[CRON] [{datetime.now().strftime('%H:%M:%S')}] Running summary cycle...")
        try:
            summary = await run_summary()
            self.last_summary = datetime.now()
            
            if summary.get("new_winners"):
                print(f"[CRON] New winners found: {len(summary['new_winners'])}")
        except Exception as e:
            print(f"[CRON] Summary failed: {e}")
    
    async def run(self):
        """Main scheduler loop."""
        print(f"[CRON] Starting optimizer cron...")
        print(f"[CRON] Optimization: every {OPTIMIZATION_INTERVAL}s")
        print(f"[CRON] Summary: every {SUMMARY_INTERVAL}s")
        
        # Initial run
        await self.run_optimization()
        
        next_optimization = time.time() + OPTIMIZATION_INTERVAL
        next_summary = time.time() + SUMMARY_INTERVAL
        
        while self.running:
            current_time = time.time()
            
            # Check if it's time for optimization
            if current_time >= next_optimization:
                await self.run_optimization()
                next_optimization = current_time + OPTIMIZATION_INTERVAL
            
            # Check if it's time for summary
            if current_time >= next_summary:
                await self.run_summary()
                next_summary = current_time + SUMMARY_INTERVAL
            
            # Sleep a bit before next check
            await asyncio.sleep(10)
        
        print("[CRON] Stopped.")


async def quick_run():
    """Quick single run for testing."""
    print("[CRON] Quick run mode...")
    await run_cycle()
    await run_summary()
    print("[CRON] Done.")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Optimizer Cron")
    parser.add_argument("--quick", action="store_true", help="Run once and exit")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon (default)")
    
    args = parser.parse_args()
    
    if args.quick:
        asyncio.run(quick_run())
    else:
        cron = OptimizerCron()
        asyncio.run(cron.run())


if __name__ == "__main__":
    main()
