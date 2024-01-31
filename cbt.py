import logging
from besser.bot.core.bot import Bot
from besser.bot.core.session import Session

from agent import Agent
from langchain.memory import ConversationBufferMemory
from enum import Enum
import json
import sys
from dotenv import load_dotenv, find_dotenv
import socket

import os
_ = load_dotenv(find_dotenv()) 

llm = Agent()

if os.environ['OPENAI_API_TYPE'] == "openai":
    llm.set_chatopenai_llm()
elif os.environ['OPENAI_API_TYPE'] == "azure":
    llm.set_azurechat_llm()

# Configure the logging module
logging.basicConfig(level=logging.INFO, format='{levelname} - {asctime}: {message}', style='{')

# Create the bot
bot = Bot('CBT_BOT')
# Load bot properties stored in a dedicated file
bot.load_properties('config.ini')
# Define the platform your chatbot will use
websocket_platform = bot.use_websocket_platform(use_ui=False)

# STATES

initial_state = bot.new_state('initial_state', initial=True)
bad_situation_state = bot.new_state('bad_situation_state')
question_state = bot.new_state('question_state')
incomplete_state = bot.new_state('incomplete_state')
recommendation_state = bot.new_state('recommendation_state')
end_cbt_state = bot.new_state('end_cbt_state')

# INTENTS

hello_intent = bot.new_intent('hello_intent', [
    'hello',
    'hi',
])

bad_situation_intent= bot.new_intent('bad_situation_intent', [
    'bad',
    'awful',
])

question_intent= bot.new_intent('question_intent', [
    'adversity event',
])

incomplete_intent= bot.new_intent('incomplete_intent', [
    'incomplete information',
])


recommendation_intent = bot.new_intent('recommendation_intent', [
    'cbt',
])

end_cbt_intent = bot.new_intent('end_cbt_intent', [
    'thanks',
    'THANKS',
    'thank you',
    'good',
])

class bot_messages(Enum):
    disclaimer = """Please remember: \n\n 
                I am not a professional, I am just a bot.\n\tIf you need more help, please contact a professional.\nYou can find more information about CBT in the following link: https://www.nhs.uk/conditions/cognitive-behavioural-therapy-cbt/"""
    initial = """Hi! I am a bot to simulate a CBT treatment. My purpose is to help you recognize fallacies in your way of thinking.
                I will ask you about a situation that made you feel bad, and I will try to help you to think about it in a more positive way.
                Did you had any negative thoughts or feelings recently?"""
    options = ['Yes, I had bad thoughts or feelings.', 'No, I am good.']
    bad_situation = """Please tell me about a situation that made you feel bad."""
    end_recommendation = """Does this help you to think about it in a more positive way?"""
    end_options = ['It does not help. I still feel bad.', 'Yes, it helps. I am good now.']
    end_cbt = """I hope you feel better now. Thanks for your time and have a nice day!"""
    fallback = """I'm here to support you. Whenever you feel comfortable, please feel free to share the situation that made you feel bad. 
                Remember, I'm here to help you think about it in a more positive way.
                Can you please provide more information about the situation that made you feel bad?"""


# STATES BODIES' DEFINITION + TRANSITIONS

def initial_body(session: Session):
    """Initial state body to be executed when the bot is started."""
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
    session.set('bot_memory', memory)
    llm.set_memory(memory)

    session.reply(bot_messages.initial.value)
    memory.chat_memory.add_user_message(bot_messages.initial.value)
    websocket_platform.reply_options(session, bot_messages.options.value)
    
initial_state.set_body(initial_body)
initial_state.when_intent_matched_go_to(bad_situation_intent, bad_situation_state)
initial_state.when_intent_matched_go_to(end_cbt_intent, end_cbt_state)

def extract_abc_information(session: Session):
    """Extract ABC (Activating Event, Belief, Consequence) information from the user message and store it as structured data."""
    cbt_struct_data: str = session.get('cbt_struct_data')
    print("extract_abc_information", type(cbt_struct_data), cbt_struct_data)

    response = llm.extract_abc_information(session.message)
    if not (cbt_struct_data is None): print(cbt_struct_data, 'cbt before combine:', len(cbt_struct_data))
    print(response, 'response before combine:', len(response))
    if cbt_struct_data is None:
        cbt_struct_data = "[]"
    response = llm.combine_abc_information(abc_json=cbt_struct_data, input=json.dumps(response, indent = 4))
    print(response, 'response after combine:', len(response))
    session.set('cbt_struct_data', response)

def bad_situation_body(session: Session):
    """Bad situation state body to be executed when the user has selected that he had a bad situation."""
    cbt_struct_data = None
    session.set('cbt_struct_data', cbt_struct_data)

    session.reply(bot_messages.bad_situation.value)
    memory: ConversationBufferMemory = session.get('bot_memory')
    memory.chat_memory.add_user_message(bot_messages.bad_situation.value)

def has_correct_format(session: Session):
    """Check if the cbt_struct_data has the correct format with inforamtion extracted from the chat conversation."""
    if session.get('cbt_struct_data') is None:
        return False
    
    cbt_struct_data: str = session.get('cbt_struct_data')
    cbt_struct_data = json.loads(cbt_struct_data)
    print("has_correct_format", cbt_struct_data)
    if not isinstance(cbt_struct_data, list):
        cbt_struct_data = None
        session.set('cbt_struct_data', cbt_struct_data)
        return False
    
    return True

def check_cbt_json(session: Session, event_params: dict):  
    """Check if the cbt_struct_data in json requires to be completed by asking further questions."""
    if not has_correct_format(session):
        return True
    
    cbt_struct_data: str = session.get('cbt_struct_data')
    cbt_struct_data = json.loads(cbt_struct_data)
    print("check_cbt_json", cbt_struct_data)

    for s in cbt_struct_data:
        if s["beliefs_in_event"] == "":
            return True
    return False

bad_situation_state.set_body(bad_situation_body)
bad_situation_state.when_intent_matched_go_to(end_cbt_intent, end_cbt_state)
bad_situation_state.when_event_go_to(check_cbt_json, question_state, event_params={})


def question_body(session: Session):
    """Question state body to be executed when the structured data is still incomplete."""
    extract_abc_information(session)
    response = llm.belief_questions(session.message)

    session.reply(response)

def is_cbt_complete(session: Session, event_params: dict):
    """Check if the cbt_struct_data in json is complete to generate a recommendation."""
    if not has_correct_format(session):
        return False
    
    cbt_struct_data: str = session.get('cbt_struct_data')
    cbt_struct_data = json.loads(cbt_struct_data)
    print("is_cbt_complete", cbt_struct_data)

    for s in cbt_struct_data:
        if "" in s.values():
            return False
    
    return True

def is_cbt_incomplete(session: Session, event_params: dict):
    """Check if the cbt_struct_data in json is incomplete to request more information from the user."""
    return not is_cbt_complete(session, event_params)

question_state.set_body(question_body)
question_state.when_intent_matched_go_to(end_cbt_intent, end_cbt_state)
question_state.when_event_go_to(is_cbt_complete, recommendation_state, event_params={})
question_state.when_event_go_to(is_cbt_incomplete, incomplete_state, event_params={})


def incomplete_body(session: Session):
    """Incomplete state body to be executed when the structured data is still incomplete."""
    extract_abc_information(session)
    cbt_struct_data: str = session.get('cbt_struct_data')
    response = llm.complete_questions(abc_json=cbt_struct_data, input=session.message)
    session.reply(response)


incomplete_state.set_body(incomplete_body)
incomplete_state.when_intent_matched_go_to(end_cbt_intent, end_cbt_state)
incomplete_state.when_event_go_to(is_cbt_complete, recommendation_state, event_params={})
incomplete_state.when_event_go_to(is_cbt_incomplete, question_state, event_params={})


def recommendation_body(session: Session):
    """Recommendation state body to be executed when the structured data is complete."""
    extract_abc_information(session)
    cbt_struct_data: str = session.get('cbt_struct_data')
    response = llm.counterarguments_for_fallacies(cbt_struct_data)
    session.reply(response)
    session.reply(bot_messages.end_recommendation.value)
    websocket_platform.reply_options(session, bot_messages.end_options.value)

recommendation_state.set_body(recommendation_body)
recommendation_state.when_intent_matched_go_to(end_cbt_intent,end_cbt_state)
recommendation_state.when_intent_matched_go_to(bad_situation_intent,question_state)


def end_cbt_body(session: Session):
    """End_CBT state body to be executed when the user has selected that he does not need more help."""
    session.reply(bot_messages.end_cbt.value)

end_cbt_state.set_body(end_cbt_body)
end_cbt_state.go_to(initial_state)



def fallback_body(session: Session):
    """Fallback state body to be executed when the bot does not understand the user message.
    It has a reminder of the bot purpose and a default message to be sent to the user."""
    extract_abc_information(session)
    session.reply(bot_messages.fallback.value)
    memory: ConversationBufferMemory = session.get('bot_memory')
    memory.chat_memory.add_user_message(bot_messages.fallback.value)


bot.set_global_fallback_body(fallback_body)


if __name__ == '__main__':

    def is_port_in_use(port: int = os.environ['STREAMLIT_PORT']) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex((os.environ['STREAMLIT_HOST'], port)) == 0

    if not is_port_in_use(8765):
        bot.run()
    else: 
        sys.exit(1)

