import pytest
from orchestrator.distributed import DistributedExecutor, InMemoryTaskQueue, Worker
from orchestrator.distributed.types import TaskStatus
from orchestrator.llm.mock_llm import MockLLM
from orchestrator.llm import LLMConfig


@pytest.mark.asyncio
async def test_in_memory_queue_enqueue():
    queue = InMemoryTaskQueue()
    
    task = await queue.enqueue("Test goal", "session_1")
    
    assert task.goal == "Test goal"
    assert task.session_id == "session_1"
    assert task.status == TaskStatus.PENDING


@pytest.mark.asyncio
async def test_in_memory_queue_dequeue():
    queue = InMemoryTaskQueue()
    
    await queue.enqueue("Test goal 1")
    await queue.enqueue("Test goal 2")
    
    task = await queue.dequeue()
    assert task is not None
    assert task.goal == "Test goal 1"


@pytest.mark.asyncio
async def test_in_memory_queue_update():
    queue = InMemoryTaskQueue()
    
    task = await queue.enqueue("Test goal")
    task_id = task.task_id
    
    await queue.update_task(task_id, status=TaskStatus.RUNNING)
    
    updated = await queue.get_task(task_id)
    assert updated.status == TaskStatus.RUNNING


@pytest.mark.asyncio
async def test_in_memory_queue_stats():
    queue = InMemoryTaskQueue()
    
    await queue.enqueue("Task 1")
    task2 = await queue.enqueue("Task 2")
    await queue.update_task(task2.task_id, status=TaskStatus.RUNNING)
    
    stats = await queue.get_stats()
    assert stats.pending_tasks == 1
    assert stats.running_tasks == 1


@pytest.mark.asyncio
async def test_distributed_executor_submit():
    llm = MockLLM(LLMConfig(provider="mock"))
    executor = DistributedExecutor(llm=llm)
    
    task = await executor.submit("Test goal", "session_1")
    
    assert task.goal == "Test goal"
    assert task.status == TaskStatus.PENDING


@pytest.mark.asyncio
async def test_distributed_executor_complete_task():
    llm = MockLLM(LLMConfig(provider="mock"))
    executor = DistributedExecutor(llm=llm)
    
    task = await executor.submit("Test goal")
    
    await executor.complete_task(task.task_id, "Result")
    
    updated = await executor.get_task(task.task_id)
    assert updated.status == TaskStatus.COMPLETED
    assert updated.result == "Result"


@pytest.mark.asyncio
async def test_distributed_executor_fail_task():
    llm = MockLLM(LLMConfig(provider="mock"))
    executor = DistributedExecutor(llm=llm)
    
    task = await executor.submit("Test goal")
    
    await executor.fail_task(task.task_id, "Error occurred")
    
    updated = await executor.get_task(task.task_id)
    assert updated.status == TaskStatus.FAILED
    assert updated.error == "Error occurred"


def test_worker_registration():
    llm = MockLLM(LLMConfig(provider="mock"))
    executor = DistributedExecutor(llm=llm)
    
    worker_id = executor.register_worker("worker_1")
    assert worker_id == "worker_1"
    
    workers = executor.get_workers()
    assert len(workers) == 1
    assert workers[0]["worker_id"] == "worker_1"
    
    executor.unregister_worker("worker_1")
    workers = executor.get_workers()
    assert len(workers) == 0


@pytest.mark.asyncio
async def test_list_tasks():
    llm = MockLLM(LLMConfig(provider="mock"))
    executor = DistributedExecutor(llm=llm)
    
    await executor.submit("Task 1")
    await executor.submit("Task 2")
    await executor.submit("Task 3")
    
    tasks = await executor.list_tasks(limit=10)
    assert len(tasks) == 3