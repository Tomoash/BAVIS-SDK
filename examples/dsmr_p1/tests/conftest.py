"""Put the folder with bavis_drv_dsmr_p1 on sys.path (the BAVIS core must be on PYTHONPATH, e.g. its backend folder)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
