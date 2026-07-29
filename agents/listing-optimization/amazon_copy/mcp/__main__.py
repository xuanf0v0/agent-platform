"""Allow ``python -m amazon_copy.mcp`` as an alias for remote_probe."""

from amazon_copy.mcp.remote_probe import main

raise SystemExit(main())
