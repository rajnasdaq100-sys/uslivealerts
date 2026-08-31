"""
Runs scanner_us.py and institutional_scanner_us.py concurrently, in one
process, for one shift of the trading day. GitHub Actions jobs are capped at
6 hours, and the full US session (9:30-16:00 ET, 6.5h) doesn't fit in one
job -- so the two workflow files in .github/workflows/ each trigger one
shift (morning / afternoon) with SCAN_START_TIME / SCAN_END_TIME set via
env vars, and this script launches both bots for that shift and waits for
both to finish.

Not meant to be run outside of the shift workflows -- for local testing,
just run scanner_us.py or institutional_scanner_us.py directly.
"""

import logging
import sys
import threading

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def run_scanner():
    from scanner_us import USSwingScanner
    try:
        USSwingScanner().run_scanner_loop()
    except Exception:
        logging.exception("scanner_us crashed")


def run_institutional():
    from institutional_scanner_us import InstitutionalFlowScannerUS
    try:
        InstitutionalFlowScannerUS().run_scanner_loop()
    except Exception:
        logging.exception("institutional_scanner_us crashed")


if __name__ == "__main__":
    t1 = threading.Thread(target=run_scanner, name="scanner_us")
    t2 = threading.Thread(target=run_institutional, name="institutional_scanner_us")

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    logging.info("Both scanners finished this shift.")
    sys.exit(0)
