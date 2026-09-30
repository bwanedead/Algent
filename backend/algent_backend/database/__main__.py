"""python -m algent_backend.database [status|migrate]"""

import json
import sys

from .migrate import migrate, status

if __name__ == "__main__":
    verb = sys.argv[1] if len(sys.argv) > 1 else "status"
    if verb == "migrate":
        print(json.dumps({"applied": migrate()}, indent=2))
    elif verb == "status":
        print(json.dumps(status(), indent=2))
    else:
        sys.exit("usage: python -m algent_backend.database [status|migrate]")
