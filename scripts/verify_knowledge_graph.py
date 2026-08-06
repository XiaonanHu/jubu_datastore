"""
CI gate for the knowledge-graph YAML packs.

    python scripts/verify_knowledge_graph.py

Run as a script (like verify_migrations.py), NOT as `python -m ...` from the
repo root: repo root on sys.path[0] makes the package's logging/ subpackage
shadow the stdlib logging module and crash interpreter startup.
"""

import sys

from jubu_datastore.knowledge_graph.graph_validator import main

if __name__ == "__main__":
    sys.exit(main())
