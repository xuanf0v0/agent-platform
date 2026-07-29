from __future__ import annotations

import asyncio

from starlette.websockets import WebSocketDisconnect

import main


class DisconnectingWebSocket:
    async def accept(self) -> None:
        return None

    async def send_text(self, line: str) -> None:
        raise WebSocketDisconnect(code=1006)


def test_log_socket_swallows_disconnect_while_sending_history(monkeypatch) -> None:
    queue: asyncio.Queue = asyncio.Queue()
    unsubscribed: list[tuple[str, asyncio.Queue]] = []
    monkeypatch.setattr(main.process_manager, "get_logs", lambda agent_id, tail: ["old log"])
    monkeypatch.setattr(main.process_manager, "subscribe_logs", lambda agent_id: queue)
    monkeypatch.setattr(
        main.process_manager,
        "unsubscribe_logs",
        lambda agent_id, value: unsubscribed.append((agent_id, value)),
    )

    asyncio.run(main.ws_agent_logs(DisconnectingWebSocket(), "listing-optimization"))

    assert unsubscribed == [("listing-optimization", queue)]
