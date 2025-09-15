import asyncio

from realtime_voicebot.transport.events import Dispatcher


def test_on_registers_handlers():
    async def main():
        dispatcher = Dispatcher()
        called: list[str] = []

        @dispatcher.on("decorated")
        async def decorated(ev):
            called.append(ev["msg"])

        async def direct(ev):
            called.append(ev["msg"])

        dispatcher.on("direct", direct)

        await dispatcher.dispatch({"type": "decorated", "msg": "a"})
        await dispatcher.dispatch({"type": "direct", "msg": "b"})

        assert called == ["a", "b"]

    asyncio.run(main())
