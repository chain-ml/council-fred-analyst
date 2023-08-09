from council.runners import Budget
from council.contexts import AgentContext, ChatHistory
from council.agents import Agent
from council.chains import Chain
from council.llm.openai_llm_configuration import OpenAILLMConfiguration
from council.llm.openai_llm import OpenAILLM

import dotenv

dotenv.load_dotenv()

import sys
from string import Template
import toml
import logging
import os


logging.getLogger("council").setLevel(logging.INFO)

sys.path.append("../agent")
from skills import (
    FredDataSpecialist,
    PythonCodeEditorSkill,
    ParsePythonSkill,
    PythonExecutionSkill,
    GeneralSkill,
)
from council_controller import LLMInstructController
from evaluator import BasicEvaluatorWithSource


class AgentApp:
    def __init__(self):
        self.context = AgentContext(chat_history=ChatHistory())
        self.llm = OpenAILLM(config=OpenAILLMConfiguration.from_env())
        self.load_prompts()
        self.init_skills()
        self.init_chains()
        self.init_controller()
        self.init_evaluator()
        self.init_agent()

    def load_prompts(self):
        # Load prompts and prompt templates
        
        self.fred_system_prompt = toml.load("../agent/prompts/fred_data_specialist_prompts.toml")[
            "system_message"
        ]["prompt"]

        self.fred_prompt_template = Template(
            toml.load("../agent/prompts/fred_data_specialist_prompts.toml")["main_prompt"]["prompt"]
        )

        self.code_header = toml.load("../agent/prompts/description.toml")["code_header"][
            "code"
        ]
        self.code_editor_system_prompt = toml.load(
            "../agent/prompts/code_editor_prompt.toml"
        )["system_message"]["prompt"]

        self.code_editor_prompt_template = Template(
            toml.load("../agent/prompts/code_editor_prompt.toml")["main_prompt"][
                "prompt"
            ]
        )
        self.code_correction_system_prompt = toml.load(
            "../agent/prompts/code_correction_prompt.toml"
        )["system_message"]["prompt"]
        self.code_correction_prompt_template = Template(
            toml.load("../agent/prompts/code_correction_prompt.toml")["main_prompt"][
                "prompt"
            ]
        )

    def init_skills(self):
        """
        FRED Data Specialist
        """
        self.fred_data_specialist = FredDataSpecialist(
            self.llm,
            system_prompt=self.fred_system_prompt,
            main_prompt_template=self.fred_prompt_template,
            code_header=self.code_header,
        )

        """
        Specialized Python code EDITING skill for daily securities price analysis.
        """
        self.code_editing_skill = PythonCodeEditorSkill(
            self.llm,
            system_prompt=self.code_editor_system_prompt,
            editor_prompt_template=self.code_editor_prompt_template,
            code_header=self.code_header,
        )

        """
        Validate/parse Python code block - could easily be generalized to regex pattern matching skill.
        """
        self.parse_python_skill = ParsePythonSkill()

        """
        Execute Python code locally in host environment - UNSAFE.
        """
        self.python_execution_skill = PythonExecutionSkill(
            self.llm,
            system_prompt=self.code_correction_system_prompt,
            error_correction_template=self.code_correction_prompt_template,
            code_header=self.code_header,
            python_bin_dir=os.environ['PYTHON_BIN_DIR']
        )

        """
        A general skill for handling other things. This is LLMSkill customized with controller "iteration" support.
        """
        self.general_skill = GeneralSkill(
            self.llm,
            system_prompt="""You are a friendly, helpful assistant. 
            Generate a brief response accoring to the provided instruction; 2 sentences at most.""",
        )

    def init_chains(self):

        self.fred_data_specialist_chain = Chain(
            name="fred_data_specialist",
            description="Identify and access economic datasets from the FRED database. Use this chain when you need to generate or edit code for accessing or downloading data from FRED.",
            runners=[self.fred_data_specialist, self.parse_python_skill]
        )

        self.code_editing_and_execution_chain = Chain(
            name="data_analysis_code_editing_and_execution",
            description="Generate/edit and execute existing Python code for data analytics and visualization. Use this chain if the user wants to generate new code or edit existing code related to data analysis.",
            runners=[
                self.code_editing_skill,
                self.parse_python_skill,
                self.python_execution_skill,
            ],
        )

        self.code_editing_chain = Chain(
            name="data_analysis_code_editing",
            description="Generate/edit (but do not execute) Python code for data analytics and visualization. Use this chain if the user wants to generate new code or edit existing code related to data analysis.",
            runners=[
                self.code_editing_skill,
                self.parse_python_skill,
            ],
        )

        self.code_execution_chain = Chain(
            name="code_execution_and_correction",
            description="Execute (but do not edit) existing Python code for data analytics and visualization. Use this chain if the user wants to run existing code.",
            runners=[
                self.parse_python_skill,
                self.python_execution_skill,
            ],
        )

        self.general_chain = Chain(
            name="general",
            description="Answer general questions without the use of any specialized skills. Use this when the user needs the answer to a question that doesn't require any coding.",
            runners=[self.general_skill],
        )

    def init_controller(self):
        self.controller = LLMInstructController(
            llm=self.llm,
            top_k_execution_plan=10,
        )

    def init_evaluator(self):
        self.evaluator = BasicEvaluatorWithSource()

    def init_agent(self):
        self.agent = Agent(
            controller=self.controller,
            chains=[
                self.fred_data_specialist_chain,
                self.code_editing_chain,
                self.code_editing_and_execution_chain,
                self.code_execution_chain,
                self.general_chain,
            ],
            evaluator=self.evaluator,
        )

    def interact(self, message, budget=1800):
        print(f"User Message: {message}")
        self.context.chatHistory.add_user_message(message)
        result = self.agent.execute(context=self.context, budget=Budget(budget))
        last_message = result.messages[-1].message
        self.context.chatHistory.add_agent_message(last_message.message)
