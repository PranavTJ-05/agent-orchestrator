import pytest
from orchestrator.events import EventBus, Event, EventType
from orchestrator.events.types import TaskStartedEvent, TaskCompletedEvent, SessionStartedEvent


@pytest.mark.asyncio
async def test_event_bus_publish_and_subscribe():
    bus = EventBus()
    received = []
    
    async def handler(event: Event):
        received.append(event)
    
    bus.subscribe(EventType.TASK_STARTED, handler)
    await bus.publish(TaskStartedEvent(
        task_id="t1",
        task_description="Test task",
        agent="test_agent",
        session_id="session_1",
    ))
    
    assert len(received) == 1
    assert received[0].event_type == EventType.TASK_STARTED
    assert received[0].data["task_id"] == "t1"


@pytest.mark.asyncio
async def test_event_bus_global_handler():
    bus = EventBus()
    received = []
    
    async def handler(event: Event):
        received.append(event)
    
    bus.subscribe_all(handler)
    await bus.publish(TaskStartedEvent(
        task_id="t1",
        task_description="Test task",
        agent="test_agent",
        session_id="session_1",
    ))
    await bus.publish(TaskCompletedEvent(
        task_id="t1",
        task_description="Test task",
        agent="test_agent",
        result="done",
        session_id="session_1",
    ))
    
    assert len(received) == 2


@pytest.mark.asyncio
async def test_event_bus_unsubscribe():
    bus = EventBus()
    received = []
    
    async def handler(event: Event):
        received.append(event)
    
    bus.subscribe(EventType.TASK_STARTED, handler)
    await bus.publish(TaskStartedEvent(
        task_id="t1",
        task_description="Test task",
        agent="test_agent",
        session_id="session_1",
    ))
    
    bus.unsubscribe(EventType.TASK_STARTED, handler)
    await bus.publish(TaskStartedEvent(
        task_id="t2",
        task_description="Test task 2",
        agent="test_agent",
        session_id="session_1",
    ))
    
    assert len(received) == 1


@pytest.mark.asyncio
async def test_event_bus_history():
    bus = EventBus(max_history=10)
    
    for i in range(15):
        await bus.publish(SessionStartedEvent(
            session_id=f"session_{i}",
            goal=f"Goal {i}",
        ))
    
    history = bus.get_history(limit=5)
    assert len(history) == 5
    
    history = bus.get_history(limit=100)
    assert len(history) == 10


@pytest.mark.asyncio
async def test_event_bus_filter_by_session():
    bus = EventBus()
    
    await bus.publish(SessionStartedEvent(session_id="session_1", goal="Goal 1"))
    await bus.publish(SessionStartedEvent(session_id="session_2", goal="Goal 2"))
    await bus.publish(SessionStartedEvent(session_id="session_1", goal="Goal 3"))
    
    history = bus.get_history(session_id="session_1")
    assert len(history) == 2
    
    history = bus.get_history(session_id="session_2")
    assert len(history) == 1


@pytest.mark.asyncio
async def test_event_bus_filter_by_type():
    bus = EventBus()
    
    await bus.publish(SessionStartedEvent(session_id="session_1", goal="Goal 1"))
    await bus.publish(TaskStartedEvent(
        task_id="t1",
        task_description="Test",
        agent="test",
        session_id="session_1",
    ))
    await bus.publish(TaskCompletedEvent(
        task_id="t1",
        task_description="Test",
        agent="test",
        result="done",
        session_id="session_1",
    ))
    
    history = bus.get_history(event_type=EventType.TASK_STARTED)
    assert len(history) == 1
    assert history[0]["event_type"] == "task_started"