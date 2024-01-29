from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain.chat_models import AzureChatOpenAI
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain.prompts import MessagesPlaceholder
from langchain.memory import ConversationBufferMemory
from langchain.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
)
from langchain.schema import SystemMessage
from langchain.utils.openai_functions import convert_pydantic_to_openai_function
from langchain.output_parsers.openai_functions import JsonKeyOutputFunctionsParser
from pydantic.v1 import BaseModel, Field
from typing import List
from enum import Enum

import logging
import traceback
from dotenv import load_dotenv, find_dotenv

import os
_ = load_dotenv(find_dotenv()) 

class prompts(Enum):
    EXTRACT = """Extract the relevant information, if not explicitly provided do not guess. Extract partial info."""
    COMBINE = """The user has provided information about adversity events, beliefs and consequences.
                Please combine the information provided by the user in JSON format."""
    QUESTIONS = """The user has provided information about adversity events, beliefs and consequences.
                Please generate two follow-up questions to understand his beliefs with more detail."""
    COMPLETE = """The user has provided information about adversity events, beliefs and consequences.
                The AI has extracted the above information, but it is incomplete.
                Please generate two follow-up questions to understand the full situation described by the user."""
    TREATMENT = """The following JSON is information about various though fallacies in the way of thinking. 
                You should provide counterarguments reflecting a positive logical way of thinking.
                Please be polite and provide a response using a a short argument. 
                Just provide one paragraph per each fallacy as an answer, do not add any additional context."""


class ABC_information(BaseModel):
    """Information adversity events, beliefs and consequences based con CBT methodology ."""
    activating_event: str = Field(description="Adversity or activating event.")
    beliefs_in_event: str = Field(description="Your beliefs about the event. It involves both obvious and underlying thoughts about situations, yourself, and others.")
    consequences: str = Field(description="Consequences, which includes your behavioral or emotional response.")

class ABC_events(BaseModel):
    """Information to extract about adversity events, beliefs and consequences."""
    abc_information: List[ABC_information] = Field(description="List of events, beliefes and consequences identified in the text.")


class Agent:
    def __init__(self):
        self._name = None
        self._llm = None
        self._memory = None

    @property   
    def name(self):
        return self._name
    
    @property
    def llm(self):
        return self._llm
    
    def set_azurechat_llm(self):
        self._name = "azure"
        #self._name = "bot-besser"
        try:
            self._llm = AzureChatOpenAI(azure_deployment=os.environ['AZURE_DEPLOYMENT_NAME'], temperature=0)
        except Exception as _:
            logging.error(f"An error occurred configuring LLM '{self._name}', deployment'{os.environ['AZURE_DEPLOYMENT_NAME']}' in endpoint '{os.environ['AZURE_OPENAI_ENDPOINT']}'."
                              f"See the attached exception:")
            traceback.print_exc()
    
    def set_chatopenai_llm(self):
        self._name = "openai"
        try:
            self._llm = ChatOpenAI(temperature=0, openai_api_key=os.environ['OPENAI_API_KEY'])
        except Exception as _:
            logging.error(f"An error occurred configuring LLM '{self._name}' in API '{os.environ['OPENAI_API_BASE']}'."
                              f"See the attached exception:")
            traceback.print_exc()
    
    def set_memory(self, memory: ConversationBufferMemory):
        self._memory = memory

    def chain_prompt(self, sysMessage:str):
        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessage(
                    content=sysMessage
                ),
                MessagesPlaceholder(
                    variable_name="chat_history"
                ),
                HumanMessagePromptTemplate.from_template(
                    "{human_input}"
                ),
            ]
        )
        return prompt
    
    def extract_abc_information(self, input:str):
        prompt = ChatPromptTemplate.from_messages([
            ("system", prompts.EXTRACT.value),
            ("human", "{input}")
        ])
        extraction_functions = [convert_pydantic_to_openai_function(ABC_events)]
        extraction_model_entities = self._llm.bind(functions=extraction_functions, function_call={"name": "ABC_events"})
        extraction_chain_entities = prompt | extraction_model_entities | JsonKeyOutputFunctionsParser(key_name="abc_information")
        return extraction_chain_entities.invoke({"input": input})
    
    def combine_abc_information(self, abc_json:str, input: str):
        abc_memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
        abc_memory.chat_memory.add_ai_message(abc_json)
        prompt = self.chain_prompt(sysMessage=prompts.COMBINE.value)
        llm_chain = LLMChain(prompt=prompt, llm=self._llm , verbose=False, memory=abc_memory)
        response = llm_chain.predict(human_input=input)
        return response
    
    def belief_questions(self, input:str):
        prompt = self.chain_prompt(sysMessage=prompts.QUESTIONS.value)
        llm_chain = LLMChain(prompt=prompt, llm=self._llm , verbose=False, memory=self._memory)
        response = llm_chain.predict(human_input=input)
        return response
    
    def complete_questions(self, abc_json:str, input:str):
        abc_memory = self._memory.copy()
        abc_memory.chat_memory.add_ai_message(abc_json)
        prompt = self.chain_prompt(sysMessage=prompts.COMPLETE.value)
        llm_chain = LLMChain(prompt=prompt, llm=self._llm , verbose=False, memory=abc_memory)
        response = llm_chain.predict(human_input=input)
        return response
    
    def counterarguments_for_fallacies(self, input:str):
        prompt = self.chain_prompt(sysMessage=prompts.TREATMENT.value)
        llm_chain = LLMChain(prompt=prompt, llm=self._llm , verbose=False, memory=self._memory)
        response = llm_chain.predict(human_input=input)
        return response


agent = Agent()
agent.set_azurechat_llm()
abc_json = "[{'activating_event': 'BAD', 'beliefs_in_event': '', 'consequences': ''}]"
input = "[{'activating_event': 'divorce', 'beliefs_in_event': 'I didn’t want this divorce', 'consequences': 'I have been very depressed about it'}, {'activating_event': 'divorce', 'beliefs_in_event': 'she divorced me', 'consequences': 'I must be the world’s biggest loser'}]"
#response = agent.combine_abc_information(abc_json=abc_json, input=input)
#print(response)