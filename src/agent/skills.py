from council.skills import SkillBase
from council.contexts import ChatMessage, ChainContext
from council.runners import Budget
from council.llm import LLMBase, LLMMessage

from code_sandbox import run_code_in_sandbox

import ast
import logging
import re
from string import Template
from typing import List, Dict

logger = logging.getLogger("council")

class FredDataSpecialist(SkillBase):
    """Specialized skill to retrieve data from FRED."""

    def __init__(
        self,
        llm: LLMBase,
        system_prompt: str,
        main_prompt_template: Template,
        code_header: str,
    ):
        """Build a new FredDataSpecialist."""

        super().__init__(name="FredDataSpecialist")
        self.llm = llm
        self.system_prompt = LLMMessage.system_message(system_prompt)
        self.main_prompt_template = main_prompt_template
        self.code_header = code_header

    def execute(self, context: ChainContext, _budget: Budget) -> ChatMessage:
        """Execute `FredDataSpecialist`."""
        
        # Get the code
        code = context.last_message.data['code']

        main_prompt = self.main_prompt_template.substitute(
            code_header=self.code_header,
            task=context.last_message.message,
            existing_code=code,
        )

        messages_to_llm = [
            self.system_prompt,
            LLMMessage.assistant_message(
                main_prompt
            ),
        ]

        llm_response = self.llm.post_chat_request(messages=messages_to_llm).first_choice

        logger.debug(f"{self.name}, generated code: {llm_response}")

        return ChatMessage.skill(
            source=self.name,
            message="I've generated code for you and placed it in the 'data' field.",
            data= context.last_message.data | {'code': llm_response},
        )


class PythonCodeEditorSkill(SkillBase):
    """Specialized skill to edit Python code for specific data analytics use cases."""

    def __init__(
        self,
        llm: LLMBase,
        system_prompt: str,
        editor_prompt_template: Template,
        code_header: str,
    ):
        """Build a new PythonDataAnalystSkill."""

        super().__init__(name="PythonCodeEditorSkill")
        self.llm = llm
        self.system_prompt = LLMMessage.system_message(system_prompt)
        self.editor_prompt_template = editor_prompt_template
        self.code_header = code_header

    def execute(self, context: ChainContext, _budget: Budget) -> ChatMessage:
        """Execute `PythonCodeEditorSkill`."""

        # Get the code
        code = context.last_message.data['code']

        editor_prompt = self.editor_prompt_template.substitute(
            existing_code=code,
            code_header=self.code_header,
            task=context.last_message.message,
        )

        messages_to_llm = [
            self.system_prompt,
            LLMMessage.assistant_message(
               editor_prompt
            ),
        ]

        llm_response = self.llm.post_chat_request(messages=messages_to_llm).first_choice

        logger.debug(f"{self.name}, generated code: {llm_response}")

        return ChatMessage.skill(
            source=self.name,
            message="I've edited code for you and placed the result in the 'data' field.",
            data=context.last_message.data | {'code': llm_response},
        )


class ParsePythonSkill(SkillBase):
    def __init__(self):
        super().__init__(name="ParsePythonSkill")

    def execute(self, context: ChainContext, budget: Budget) -> ChatMessage:

        # Get the code
        code = context.last_message.data['code']

        try:
            ast.parse(code)
            return ChatMessage.skill(
                source=self.name, message="Parsing succeded.", data=context.last_message.data | {'code': code}
            )
        except SyntaxError:
            pass

        pattern = r"```python\s+(.*?)\s+```"
        matches = re.findall(pattern, code, re.DOTALL)
        if matches:
            python_code = None
            for match in matches:
                python_code = match
            message = "Parsing succeeded."
            return ChatMessage.skill(
                source=self.name, message=message, data=context.last_message.data | {'code': python_code}
            )
        else:
            message = "Parsing failed."
            return ChatMessage.skill(source=self.name, message=message, data=context.last_message.data | {'code': python_code}, is_error=True)


class PythonExecutionSkill(SkillBase):
    def __init__(
        self,
        llm: LLMBase,
        system_prompt: str,
        error_correction_template: Template,
        code_header: str,
        python_bin_dir: str,
    ):
        super().__init__(name="PythonExecutionSkill")
        self.llm = llm
        self.system_prompt = system_prompt
        self.error_correction_template = error_correction_template
        self.code_header = code_header
        self.python_bin_dir = python_bin_dir

    def error_correction(self, code, error, conversation_history, task):
        error_correction_llm_input = self.error_correction_template.substitute(
            conversation_history=conversation_history,
            task=task,
            code=code,
            code_header=self.code_header,
            error_message=error,
        )

        messages_to_llm = [
            LLMMessage.system_message(self.system_prompt),
            LLMMessage.assistant_message(error_correction_llm_input),
        ]
        llm_response = self.llm.post_chat_request(messages=messages_to_llm).first_choice
        logger.debug(f"{self.name}, corrected code: {llm_response}")
        return llm_response

    def execute_code(self, data, code):

        is_code = False
        try:
            ast.parse(code)
            is_code = True
        except SyntaxError:
            pass

        if not is_code:
            pattern = r"```python\s+(.*?)\s+```"
            matches = re.findall(pattern, code, re.DOTALL)
            if matches:
                python_code = None
                for match in matches:
                    python_code = match
                code = python_code
            else:
                message = "Parsing failed."
                logger.debug(f"{self.name}, failed to parse code: {code}")
                return ChatMessage.skill(source=self.name, message=message, data={'code': code}, is_error=True)

        try:
            # Run the Python file as a subprocess
            exec_result = run_code_in_sandbox(code, self.python_bin_dir)

            data = data | {
                "code": code,
                "stdout": exec_result['stdout'],
                "stderr": exec_result['stderr'],
            }
            if exec_result["returncode"] == 0:
                logger.debug(f"{self.name}, executed code: {data}")
                message_to_user = data['stdout'].strip()
                if len(message_to_user) < 1:
                    message_to_user = "Python code executed successfully."
                return ChatMessage.skill(
                    source=self.name,
                    message=message_to_user,
                    data=data,
                )
            else:
                logger.debug(f"{self.name}, failed to execute code: {data}")
                return ChatMessage.skill(
                    source=self.name,
                    message=f"Python code execution failed. There was an error: {data['stderr']}",
                    data=data,
                    is_error=True
                )
        except Exception as e:
            data = data | {
                "code": code,
                "stdout": "",
                "stderr": "",
            }
            logger.debug(f"{self.name}, failed to execute code: {data}")
            return ChatMessage.skill(
                source=self.name,
                message=f"Exception while executing Python code:\n{e}",
                data=data,
                is_error=True
            )

    def execute(
        self, context: ChainContext, budget: Budget, num_retries=3
    ) -> ChatMessage:
        """
        Try to execute a Python file, collecting output (or error message) from the standard output.
        """

        # Get the chat message history
        message_history = [
            f"{m.kind}: {m.message}" for m in context.messages
        ]

        # We also need the conversation history
        last_message = message_history[-1]
        prior_messages = message_history[:-1]
        conversation_history = str([m for m in prior_messages])

        # Get the current chain context - the last item in the chainHistory
        code = context.last_message.data['code']

        for _ in range(num_retries):
            skill_message = self.execute_code(context.last_message.data, code)
            if isinstance(skill_message, ChatMessage):
                if len(skill_message.data['stderr']) < 1:
                    return skill_message
            
            # Will run even if stderr only has warnings
            code = self.error_correction(
                code,
                skill_message.data["stderr"],
                conversation_history,
                last_message,
            )

        return skill_message


class GeneralSkill(SkillBase):
    """Respond to questions using plain LLM call."""

    def __init__(
        self,
        llm: LLMBase,
        system_prompt: str,
    ):
        """Build a new GeneralSkill."""

        super().__init__(name="GeneralSkill")
        self.llm = llm
        self.system_prompt = LLMMessage.system_message(system_prompt)

    def execute(self, context: ChainContext, _budget: Budget) -> ChatMessage:
        """Execute `GeneralSkill`."""

        # Get the instruction
        instruction = context.last_message.message

        messages_to_llm = [
            self.system_prompt,
            LLMMessage.assistant_message(instruction)
        ]

        llm_response = self.llm.post_chat_request(messages=messages_to_llm).first_choice

        logger.debug(f"{self.name}, response: {llm_response}")

        return ChatMessage.skill(
            source=self.name,
            message=llm_response,
            data=context.last_message.data,
        )
