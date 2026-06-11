"""Core engine: blackboard store and the reactive superstep executor.

The whole engine vocabulary re-exported flat, so application code writes
`from fedotmas.engine import Fact, System, ReactiveExecutor, Goal` instead of reaching into
the submodules.
"""

from fedotmas.engine.contract import Card, Fact, Node, Result, Status, View
from fedotmas.engine.executor import Executor, ReactiveExecutor
from fedotmas.engine.node import as_node
from fedotmas.engine.policy import AuctionSelect, FireAll, Policy
from fedotmas.engine.report import Run, StepReport
from fedotmas.engine.store import Snapshot, Store
from fedotmas.engine.system import System
from fedotmas.engine.terminate import (
    Budget,
    Goal,
    Quiescence,
    Terminate,
    all_of,
    any_of,
)

__all__ = [
    "AuctionSelect",
    "Budget",
    "Card",
    "Executor",
    "Fact",
    "FireAll",
    "Goal",
    "Node",
    "Policy",
    "Quiescence",
    "ReactiveExecutor",
    "Result",
    "Run",
    "Snapshot",
    "Status",
    "StepReport",
    "Store",
    "System",
    "Terminate",
    "View",
    "all_of",
    "any_of",
    "as_node",
]
