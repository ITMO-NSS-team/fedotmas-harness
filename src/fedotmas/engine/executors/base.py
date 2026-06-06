"""Executor interface."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from fedotmas.engine.contract import Fact
from fedotmas.engine.policy import Policy
from fedotmas.engine.scheduler import Run
from fedotmas.engine.store import Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import Terminate


class Executor(Protocol):
    async def run(
        self,
        system: System,
        store: Store,
        *,
        seed: Iterable[Fact] = (),
        terminate: Terminate | None = None,
        policy: Policy | None = None,
    ) -> Run: ...
