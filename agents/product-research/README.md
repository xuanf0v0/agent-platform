# Amazon Product Research Agent

Evidence-driven Amazon US product discovery, validation, and candidate comparison.

The service is intentionally live-data only. It inherits model and MCP settings
read-only from the existing listing-optimization agent, falling back to the
listing-creation agent for missing values. Missing or incomplete evidence is
reported as a gap and is never replaced with fixture data.
