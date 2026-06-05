"""DSL for Creating Graph of Agents"""

"""
## Wokrflows

Start: Agent1,
Agent1: Agent2,
Agent2: Agent3,
Agent3: End


Start -> Agent1 -> Agent2 -> Agent3 -> End


Start: Agent1,
Agent1: Agent2,
Agent1: Agent3,
Agent2: Agent4,
Agent3: Agent4,
Agent4: End

                   Agent2
Start -> Agent1 ->        -> Agent4 -> End
                   Agent3
"""
