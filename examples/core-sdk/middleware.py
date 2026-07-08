import asyncio

from fedotmas import Middleware, action


async def flaky(x: int) -> int:
    return x + 1


async def slow(x: int) -> int:
    return x * 2


async def backup(x: int) -> int:
    return -1


class Retry(Middleware):
    def __init__(self, times: int) -> None:
        self.times = times

    async def around(self, node, input, view, call):
        for _ in range(self.times - 1):
            try:
                return await call(input, view)
            except Exception:
                pass
        return await call(input, view)


class Timeout(Middleware):
    def __init__(self, seconds: float) -> None:
        self.seconds = seconds

    async def around(self, node, input, view, call):
        return await asyncio.wait_for(call(input, view), self.seconds)


async def combinators() -> None:
    left = action(flaky).retry(3).fallback(action(backup))
    right = action(slow).timeout(2.0)
    await (left + right).run(1)


async def onion() -> None:
    pipeline = action(flaky) + action(slow)
    await pipeline.run(1, middleware=[Retry(3), Timeout(2.0)])


async def main() -> None:
    await combinators()
    await onion()


if __name__ == "__main__":
    asyncio.run(main())
