from __future__ import annotations

import logging
from typing import Any
from .types import AgentRegistration, AgentCapability, Capability

logger = logging.getLogger(__name__)


class AgentMarketplace:
    def __init__(self) -> None:
        self._agents: dict[str, AgentRegistration] = {}
        self._capability_index: dict[Capability, list[str]] = {}

    def register(self, registration: AgentRegistration) -> None:
        self._agents[registration.name] = registration
        
        for cap in registration.capabilities:
            if cap.capability not in self._capability_index:
                self._capability_index[cap.capability] = []
            if registration.name not in self._capability_index[cap.capability]:
                self._capability_index[cap.capability].append(registration.name)
        
        logger.info(f"Registered agent: {registration.name} with capabilities: {[c.capability.value for c in registration.capabilities]}")

    def unregister(self, name: str) -> bool:
        if name not in self._agents:
            return False
        
        registration = self._agents[name]
        for cap in registration.capabilities:
            if cap.capability in self._capability_index:
                if name in self._capability_index[cap.capability]:
                    self._capability_index[cap.capability].remove(name)
        
        del self._agents[name]
        logger.info(f"Unregistered agent: {name}")
        return True

    def get(self, name: str) -> AgentRegistration | None:
        return self._agents.get(name)

    def list_all(self) -> list[AgentRegistration]:
        return list(self._agents.values())

    def find_by_capability(self, capability: Capability) -> list[AgentRegistration]:
        agent_names = self._capability_index.get(capability, [])
        return [self._agents[name] for name in agent_names if name in self._agents]

    def find_best_match(
        self,
        required_capabilities: list[Capability],
        preferred_agent: str | None = None,
    ) -> AgentRegistration | None:
        candidates: dict[str, float] = {}
        
        for cap in required_capabilities:
            agents = self.find_by_capability(cap)
            for agent in agents:
                score = agent.get_capability_score(cap)
                if agent.name not in candidates:
                    candidates[agent.name] = 0.0
                candidates[agent.name] += score
        
        if not candidates:
            return None
        
        if preferred_agent and preferred_agent in candidates:
            candidates[preferred_agent] += 0.5
        
        best_name = max(candidates, key=candidates.get)
        return self._agents.get(best_name)

    def match_task(self, task_description: str, required_capabilities: list[Capability]) -> AgentRegistration | None:
        return self.find_best_match(required_capabilities)

    def get_capability_stats(self) -> dict[str, int]:
        stats = {}
        for cap, agents in self._capability_index.items():
            stats[cap.value] = len(agents)
        return stats