import pytest
from orchestrator.marketplace import AgentMarketplace, AgentRegistration, AgentCapability, Capability


def test_marketplace_register():
    market = AgentMarketplace()
    reg = AgentRegistration(
        name="test_agent",
        description="A test agent",
        capabilities=[
            AgentCapability(capability=Capability.CODING, score=1.0),
            AgentCapability(capability=Capability.WEB_SEARCH, score=0.8),
        ],
    )
    market.register(reg)
    
    assert market.get("test_agent") is not None
    assert market.get("test_agent").has_capability(Capability.CODING)


def test_marketplace_unregister():
    market = AgentMarketplace()
    reg = AgentRegistration(
        name="test_agent",
        description="A test agent",
        capabilities=[AgentCapability(capability=Capability.CODING)],
    )
    market.register(reg)
    
    assert market.unregister("test_agent") is True
    assert market.get("test_agent") is None


def test_marketplace_find_by_capability():
    market = AgentMarketplace()
    market.register(AgentRegistration(
        name="coder",
        description="Coding agent",
        capabilities=[AgentCapability(capability=Capability.CODING)],
    ))
    market.register(AgentRegistration(
        name="researcher",
        description="Research agent",
        capabilities=[AgentCapability(capability=Capability.RESEARCH)],
    ))
    
    coders = market.find_by_capability(Capability.CODING)
    assert len(coders) == 1
    assert coders[0].name == "coder"


def test_marketplace_find_best_match():
    market = AgentMarketplace()
    market.register(AgentRegistration(
        name="coder",
        description="Coding agent",
        capabilities=[
            AgentCapability(capability=Capability.CODING, score=1.0),
            AgentCapability(capability=Capability.WEB_SEARCH, score=0.5),
        ],
    ))
    market.register(AgentRegistration(
        name="researcher",
        description="Research agent",
        capabilities=[
            AgentCapability(capability=Capability.RESEARCH, score=1.0),
            AgentCapability(capability=Capability.WEB_SEARCH, score=1.0),
        ],
    ))
    
    best = market.find_best_match([Capability.CODING, Capability.WEB_SEARCH])
    assert best.name == "coder"
    
    best = market.find_best_match([Capability.RESEARCH, Capability.WEB_SEARCH])
    assert best.name == "researcher"


def test_marketplace_capability_stats():
    market = AgentMarketplace()
    market.register(AgentRegistration(
        name="coder",
        description="Coding agent",
        capabilities=[AgentCapability(capability=Capability.CODING)],
    ))
    market.register(AgentRegistration(
        name="researcher", 
        description="Research agent",
        capabilities=[AgentCapability(capability=Capability.CODING)],
    ))
    
    stats = market.get_capability_stats()
    assert stats[Capability.CODING.value] == 2


def test_marketplace_list_all():
    market = AgentMarketplace()
    market.register(AgentRegistration(name="a", description="a", capabilities=[]))
    market.register(AgentRegistration(name="b", description="b", capabilities=[]))
    
    all_agents = market.list_all()
    assert len(all_agents) == 2
    names = [a.name for a in all_agents]
    assert "a" in names
    assert "b" in names