import logging
from string import Template
from typing import List, Tuple

from council.contexts import (
    AgentContext,
    ScoredChatMessage,
    ChatMessage,
)

from council.chains import Chain
from council.llm import LLMMessage, LLMBase
from council.utils import Option
from council.runners import Budget
from council.controllers import ControllerBase, ExecutionUnit

logger = logging.getLogger("council")

class LLMInstructController(ControllerBase):
    """
    A LLM controller that also generates instructions for the chains it selects. 
    """

    _llm: LLMBase

    def __init__(
        self,
        llm: LLMBase,
        hints: List[str] = "",
        response_threshold: float = 0,
        top_k_execution_plan: int = 10000,
    ):
        """
        Initialize a new instance

        Parameters:
            llm (LLMBase): the instance of LLM to use
            hints (List(str)): Application-specific hints to pass to the LLM (e.g. ["If the user is asking for a recipe, always ask the 'Recipes' chain for something extra spicy."])
            response_threshold (float): a minimum threshold to select a response from its score
            top_k_execution_plan (int): maximum number of execution plan returned
        """
        self._llm = llm
        self._hints = hints
        self._response_threshold = response_threshold
        self._top_k = top_k_execution_plan

        # Controller State
        self._state = {
            "iteration": 0
        }

    def get_plan(
        self, context: AgentContext, chains: List[Chain], budget: Budget
    ) -> List[ExecutionUnit]:
        chain_details = "\n ".join(
            [f"name: {c.name}, description: {c.description}" for c in chains]
        )
        conversation_history = [f"{m.kind}: {m.message}" for m in context.chatHistory.messages]

        system_message = """
        You are the Controller module for an AI assistant. Your role is to control the execution flow by selecting and invoking chains with relevant instructions using natural language."""

        main_prompt_template = Template("""
        # TASK DESCRIPTION
        Your task is to decide which Chain is better suited to handling the USER MESSAGE and to provide natural language instructions to the selected chain.
        Consider the information in CONTROLLER STATE as you make your decision.

        # INSTRUCTIONS
        Read the following Chain details given as name and a description (name: {name}, description: {description})
        $chain_details

        - Select exactly one chain, assign a score out of 10 based on your confidence, and give the chain instructions that will best address the USER MESSAGE
        - You will answer with {name};{integer score between 0 and 10};{natural language instructions for the selected chain}
        - When no category is relevant, you will answer exactly with 'unknown'

        # HINTS
        $hints
                                        
        # CONTROLLER STATE
        $controller_state

        # CONVERSATION HISTORY
        $conversation_history

        # USER MESSAGE
        $user_message

        # Controller Decision (formatted precisely as {name};{integer score between 0 and 10};{natural language instructions for the selected chain})
        """)

        main_prompt = main_prompt_template.substitute(
            chain_details=chain_details,
            hints='\n'.join(self._hints),
            controller_state=self._state,
            conversation_history='\n'.join(conversation_history),
            user_message=conversation_history[-1]
        )

        messages = [
            LLMMessage.system_message(system_message),
            LLMMessage.user_message(main_prompt),
        ]

        response = self._llm.post_chat_request(messages).first_choice
        logger.debug(f"llm response: {response}")

        parsed = [self.parse_line(line, chains) for line in response.strip().splitlines()]
        filtered = [
            r.unwrap()
            for r in parsed
            if r.is_some() and r.unwrap()[1] > self._response_threshold
        ]
        if (filtered is None) or (len(filtered) == 0):
            return []

        filtered.sort(key=lambda item: item[1], reverse=True)
        result = []
        for chain, score, instructions in filtered:
            if chain is not None:
                exec_unit = ExecutionUnit(
                    chain,
                    budget,
                    initial_state=ChatMessage.chain(
                        message=instructions,
                        data=self._state | {"iteration": self._state["iteration"]},
                    ),
                    name=f"{chain.name};{score}",
                )
                result.append(exec_unit)
                logger.info(f"Controller Message: {chain.name};{score};{instructions}")

        controller_result = result[: self._top_k]
        return controller_result

    @staticmethod
    def parse_line(line: str, chains: List[Chain]) -> Option[Tuple[Chain, int, str]]:
        result: Option[Tuple[Chain, int, str]] = Option.none()
        try:
            (name, score, instructions) = line.split(";", 3)
            chain = next(filter(lambda item: item.name == name, chains))
            result = Option.some((chain, int(score), instructions))
        finally:
            return result

    def select_responses(self, context: AgentContext) -> List[ScoredChatMessage]:
        
        # Get the "last" results from each chain
        all_eval_results = context.last_evaluator_iteration()

        # Only include results from the current iteration
        current_iteration_results = []
        for scored_result in all_eval_results:
            message = scored_result.message
            logger.debug(f"eval result from iteration {message.data['iteration']}: {message}, {message.data}")
            if isinstance(message.data, dict):
                if message.data["iteration"] == self._state["iteration"]:
                    current_iteration_results.append(scored_result)

        # Sort the results based on the Evaluator's score
        current_iteration_results = sorted(current_iteration_results, key=lambda x: x.score, reverse=True)
        logger.debug(f"select_responses result at iteration {self._state['iteration']}: {current_iteration_results}")

        # Get the top result
        scored_message = current_iteration_results[0]

        # Update the controller state
        self._state |= scored_message.message.data

        # Increment the controller iteration
        self._state["iteration"] += 1
        
        # Return only the top result
        return [scored_message]
    