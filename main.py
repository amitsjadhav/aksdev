“””
main.py — Entry point.  Starts the polling loop.
“””

import logging
import signal
import sys
import time

# src/ is the working directory inside the container

from config import Config
from listener import MQSwiftListener

logging.basicConfig(
level=logging.INFO,
format=”%(asctime)s [%(levelname)s] %(name)s - %(message)s”,
handlers=[
logging.StreamHandler(sys.stdout),
logging.FileHandler(”/tmp/mq_swift_listener.log”),
],
)
logger = logging.getLogger(**name**)

def _shutdown(signum, frame):
logger.info(“Shutdown signal received — exiting.”)
sys.exit(0)

def main() -> None:
signal.signal(signal.SIGINT,  _shutdown)
signal.signal(signal.SIGTERM, _shutdown)

```
cfg = Config.from_env()
listener = MQSwiftListener(cfg)

logger.info(
    "IBM MQ SWIFT Listener started  queue=%s  poll_interval=%ss",
    cfg.mq.queue_name,
    cfg.mq.poll_interval_seconds,
)

while True:
    try:
        listener.poll()
    except SystemExit:
        raise
    except Exception as exc:
        logger.critical("Fatal error in main loop: %s", exc, exc_info=True)

    time.sleep(cfg.mq.poll_interval_seconds)
```

if **name** == “**main**”:
main()