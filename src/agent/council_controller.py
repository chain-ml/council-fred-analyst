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
        You are the Controller module for an AI assistant. Your role is to control the execution flow by generating a plan to invoke CHAINs with relevant instructions using natural language."""

        main_prompt_template = Template("""
        # TASK DESCRIPTION
        Your task is to break down the problem into a plan (an ordered sequence of instructions) that will each be handled by a CHAIN invocation.
        You will decide how best to apply your available CHAINs and respond with invocations that include natural language instructions.
        Consider the information in CONTROLLER STATE as you make your decision.
        Use your avaiable CHAINS to decide what steps to take next. 
        You are only responsible for deciding what to do next. You will delegate work to other agents via CHAINS.

        # INSTRUCTIONS
        Read the following CHAIN details given as name and a description (name: {name}, description: {description})
        $chain_details

        - Consider the CONVERSATION HISTORY and USER MESSAGE.
        - Consider the name and description of each chain and decide whether or how you want to use it. 
        - Only give instructions to relevant CHAINs.
        - Break down the request into a sequence of steps that can be handled by one or more CHAIN invocations.
        - You can decide to invoke the same CHAIN multiple times, with different instructions. 
        - Provide CHAIN instructions that are relevant towards completing your TASK.
        - Try to minimize the number of steps, and use a maximum of 10 steps.
        - You will answer with a list of one or more steps, formatted precisely as {name};{execution order between 1 and 10};{natural language instructions for the selected CHAIN}
        - When no CHAIN is relevant, you will answer exactly with 'unknown'

        # HINTS
        $hints
                                        
        # CONTROLLER STATE
        $controller_state

        # CONVERSATION HISTORY
        $conversation_history

        # USER MESSAGE
        $user_message

        # Controller Decision (formatted precisely as a plan of {name};{execution order between 1 and 10};{natural language instructions for the selected CHAIN})
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
        logger.info(f"controller llm response: {response}")

        parsed = [self.parse_line(line.strip(), chains) for line in response.splitlines()]
        logger.info(f"controller parsed: {parsed}")
        filtered = [
            r.unwrap()
            for r in parsed
            if r.is_some() and r.unwrap()[1] > self._response_threshold
        ]
        if (filtered is None) or (len(filtered) == 0):
            return []

        logger.info(f"controller filtered: {filtered}")
        filtered.sort(key=lambda item: item[1], reverse=False)
        result = []
        plan_message = []
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
                plan_message.append(f"{chain.name};{score};{instructions}")
        plan_message = '<SEP>'.join(plan_message)
        logger.info(f"Controller Message:<SEP>{plan_message}")
        logger.info(f"controller result: {result}")
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
        # current_iteration_results = sorted(current_iteration_results, key=lambda x: x.score, reverse=True)
        logger.debug(f"select_responses result at iteration {self._state['iteration']}: {current_iteration_results}")

        # Get the top result
        # scored_message = current_iteration_results[-1]

        # Iterate over results and update the state
        for scored_message in current_iteration_results:
            print(scored_message.message.data)
            self._state |= scored_message.message.data

        # Update the controller state
        # self._state |= scored_message.message.data

        # Increment the controller iteration
        self._state["iteration"] += 1
        
        # Return only the top result
        # return [scored_message]

        # Return all messages
        return current_iteration_results
    