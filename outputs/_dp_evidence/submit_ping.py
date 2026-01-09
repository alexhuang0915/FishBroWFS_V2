#!/usr/bin/env python3
import sys
sys.path.insert(0, 'src')
from control.supervisor import submit

job_id = submit("PING", {}, {"source": "test"})
print(job_id)