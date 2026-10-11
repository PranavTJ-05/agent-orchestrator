from __future__ import annotations

import logging
from typing import Any, Callable

from ..llm.base import LLM
from .types import DebateType, DebateRound, DebateResult, JudgeDecision

logger = logging.getLogger(__name__)


DEFAULT_MAX_ROUNDS = 5
PROMPT_TEMPLATE = """You are participating in a debate on the topic: {topic}

Your role: {role}
Current round: {round_number}

Previous arguments:
{previous_arguments}

Now, provide your argument. Be concise, logical, and back up your points with evidence."""


class DebateRunner:
    def __init__(
        self,
        llm: LLM,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
    ) -> None:
        self._llm = llm
        self._max_rounds = max_rounds

    async def run_agent_vs_agent(
        self,
        topic: str,
        agent_a_name: str,
        agent_a_prompt: str,
        agent_b_name: str,
        agent_b_prompt: str,
        judge_prompt: str | None = None,
    ) -> DebateResult:
        result = DebateResult(
            topic=topic,
            debate_type=DebateType.AGENT_VS_AGENT,
        )

        for round_num in range(1, self._max_rounds + 1):
            previous = "\n".join(
                f"{r.agent_name}: {r.argument}" for r in result.rounds
            )

            arg_a = await self._generate_argument(
                topic, agent_a_name, agent_a_prompt, round_num, previous
            )
            result.rounds.append(DebateRound(round_num, agent_a_name, arg_a))

            arg_b = await self._generate_argument(
                topic, agent_b_name, agent_b_prompt, round_num, previous
            )
            result.rounds.append(DebateRound(round_num, agent_b_name, arg_b))

            logger.info(f"Round {round_num} completed for debate on '{topic}'")

        decision = await self._judge_debate(topic, result.rounds)
        result.winner = decision.winner
        result.judge_score = decision.score
        result.judge_reasoning = decision.reasoning

        return result

    async def run_critic_loop(
        self,
        topic: str,
        initial_response: str,
        critique_prompt: str = "You are a critic. Provide constructive feedback.",
        revision_prompt: str = "You are a reviser. Improve the response based on feedback.",
    ) -> DebateResult:
        result = DebateResult(
            topic=topic,
            debate_type=DebateType.CRITIC_LOOP,
        )

        current_response = initial_response
        round_num = 1

        while round_num <= self._max_rounds:
            previous = "\n".join(
                f"{r.agent_name}: {r.argument}" for r in result.rounds
            )

            critique = await self._llm.generate(
                system_prompt=critique_prompt,
                messages=[{
                    "role": "user",
                    "content": f"Topic: {topic}\n\nCurrent response:\n{current_response}\n\nProvide specific, actionable feedback."
                }],
            )
            result.rounds.append(DebateRound(round_num, "critic", critique[0]))

            revision = await self._llm.generate(
                system_prompt=revision_prompt,
                messages=[{
                    "role": "user",
                    "content": f"Topic: {topic}\n\nOriginal response:\n{current_response}\n\nCritique:\n{critique[0]}\n\nProvide an improved response addressing the critique."
                }],
            )
            current_response = revision[0]
            result.rounds.append(DebateRound(round_num, "reviser", current_response))

            logger.info(f"Critic loop round {round_num} completed")

            if self._should_conclude_critic(result.rounds):
                break

            round_num += 1

        result.winner = "reviser"
        result.judge_reasoning = f"Completed {len(result.rounds)} rounds of critique and revision"

        return result

    async def _generate_argument(
        self,
        topic: str,
        agent_name: str,
        role_prompt: str,
        round_num: int,
        previous_arguments: str,
    ) -> str:
        content, _ = await self._llm.generate(
            system_prompt=role_prompt,
            messages=[{
                "role": "user",
                "content": PROMPT_TEMPLATE.format(
                    topic=topic,
                    role=role_prompt,
                    round_number=round_num,
                    previous_arguments=previous_arguments or "No previous arguments yet.",
                ),
            }],
        )
        return content

    async def _judge_debate(
        self,
        topic: str,
        rounds: list[DebateRound],
    ) -> JudgeDecision:
        arguments_text = "\n\n".join(
            f"Round {r.round_number} - {r.agent_name}:\n{r.argument}"
            for r in rounds
        )

        judge_prompt = f"""You are a judge evaluating a debate on: {topic}

Evaluate the arguments and determine the winner based on:
1. Logical reasoning and evidence
2. Clarity and persuasiveness
3. Addressing counterarguments

Debate arguments:
{arguments_text}

Provide your decision in this format:
WINNER: [agent_name]
SCORE: [0-10]
REASONING: [2-3 sentence explanation]"""

        content, _ = await self._llm.generate(
            system_prompt="You are a fair and objective debate judge.",
            messages=[{"role": "user", "content": judge_prompt}],
        )

        return self._parse_judge_response(content)

    def _parse_judge_response(self, response: str) -> JudgeDecision:
        lines = response.strip().split("\n")
        winner = "unknown"
        score = 5.0
        reasoning = response

        for line in lines:
            if line.startswith("WINNER:"):
                winner = line.replace("WINNER:", "").strip()
            elif line.startswith("SCORE:"):
                try:
                    score = float(line.replace("SCORE:", "").strip())
                except ValueError:
                    pass
            elif line.startswith("REASONING:"):
                reasoning = line.replace("REASONING:", "").strip()

        return JudgeDecision(
            winner=winner,
            score=score,
            reasoning=reasoning,
        )

    def _should_conclude_critic(self, rounds: list[DebateRound]) -> bool:
        if len(rounds) < 2:
            return False
        last_critique = None
        last_revision = None
        for r in reversed(rounds):
            if r.agent_name == "critic" and last_critique is None:
                last_critique = r.argument
            if r.agent_name == "reviser" and last_revision is None:
                last_revision = r.argument
            if last_critique and last_revision:
                break
        if not last_critique or not last_revision:
            return False
        return len(last_critique) < 50 or len(last_revision) < 50