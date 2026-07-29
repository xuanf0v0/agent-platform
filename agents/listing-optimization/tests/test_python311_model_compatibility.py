from amazon_copy.automatic_models import AutomaticResearchCache
from amazon_copy.mcp.live_research_models import McpCallRecord, McpToolSnapshot
from amazon_copy.mcp.remote_http import RemoteProbeSummary
from pydantic import TypeAdapter


def test_automatic_research_cache_builds_with_supported_typed_dicts() -> None:
    # Given: one tool snapshot containing the TypedDict call record used by the cache.
    call = McpCallRecord(tool="keyword_research", ok=True, summary_text="keyword")
    snapshot = McpToolSnapshot(
        provider="provider",
        status="ok",
        tool_count=1,
        calls=[call],
    )

    # When: Pydantic builds and validates the cache on the supported interpreter.
    cache = AutomaticResearchCache(
        source_fingerprint="source-fingerprint",
        query="query",
        snapshots=(snapshot,),
    )

    # Then: the nested TypedDict survives schema construction and validation.
    assert cache.snapshots[0].calls == [call]


def test_remote_probe_summary_builds_a_pydantic_adapter() -> None:
    # Given: the remote-probe TypedDict used at the MCP transport boundary.
    summary = RemoteProbeSummary(
        name="provider",
        ok=True,
        tool_count=0,
        tool_names=[],
        error_code=None,
        error_message=None,
        fixture=False,
        called_tool=None,
    )

    # When: a Pydantic adapter traverses the transport summary schema.
    validated = TypeAdapter(RemoteProbeSummary).validate_python(summary)

    # Then: Python 3.11 can validate the full summary without a user error.
    assert validated == summary
