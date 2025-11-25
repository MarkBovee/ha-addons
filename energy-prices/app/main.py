"""Energy Prices add-on main entry point."""

import logging
import signal
import sys
import time
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Shutdown flag for graceful termination
shutdown_flag = False


def signal_handler(signum, frame):
    """Handle SIGTERM and SIGINT for graceful shutdown."""
    global shutdown_flag
    logger.info("Received signal %s, initiating graceful shutdown...", signum)
    shutdown_flag = True


def main():
    """Main entry point for the add-on."""
    logger.info("Energy Prices add-on starting...")
    
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Placeholder - will be implemented in Phase 4
    logger.warning("Main loop not yet implemented - Phase 1 structure complete")
    
    # Keep running until shutdown
    try:
        while not shutdown_flag:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        logger.info("Energy Prices add-on stopped")


if __name__ == "__main__":
    main()
