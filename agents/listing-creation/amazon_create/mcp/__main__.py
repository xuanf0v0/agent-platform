"""Allow ``python -m amazon_create.mcp`` as an alias for remote_probe."""

from amazon_create.mcp.remote_probe import main

raise SystemExit(main())
