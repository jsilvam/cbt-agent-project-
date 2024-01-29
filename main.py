import logging
from besser.bot.core.bot import Bot
from besser.bot.core.session import Session

from agent import Agent
from langchain.memory import ConversationBufferMemory
from enum import Enum
import json

llm = Agent()
#llm.set_chatopenai_llm()
llm.set_azurechat_llm()

# Configure the logging module
logging.basicConfig(level=logging.INFO, format='{levelname} - {asctime}: {message}', style='{')

# Create the bot
bot = Bot('CBT_BOT')
# Load bot properties stored in a dedicated file
bot.load_properties('config.ini')
# Define the platform your chatbot will use
websocket_platform = bot.use_websocket_platform(use_ui=True)

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
                Remember, I'm here to help you think about it in a more positive way.}"""


# STATES BODIES' DEFINITION + TRANSITIONS

def initial_body(session: Session):
    session.reply(bot_messages.disclaimer.value)
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
    session.set('bot_memory', memory)
    llm.set_memory(memory)

    session.reply(bot_messages.initial.value)
    memory.chat_memory.add_user_message(bot_messages.initial.value)
    websocket_platform.reply_options(session, bot_messages.options.value)
    
initial_state.set_body(initial_body)
initial_state.when_intent_matched_go_to(bad_situation_intent, bad_situation_state)
initial_state.when_intent_matched_go_to(end_cbt_intent, end_cbt_state)


def bad_situation_body(session: Session):
    #session.reply("SITUATION")

    cbt_struct_data = None
    session.set('cbt_struct_data', cbt_struct_data)

    session.reply(bot_messages.bad_situation.value)
    memory: ConversationBufferMemory = session.get('bot_memory')
    memory.chat_memory.add_user_message(bot_messages.bad_situation.value)



def check_cbt_json(session: Session, event_params: dict):
    print("check_cbt_json", session.get('cbt_struct_data'))
    #if event_params is not None:
    return True
    #else:
        #return False

bad_situation_state.set_body(bad_situation_body)
bad_situation_state.when_intent_matched_go_to(end_cbt_intent, end_cbt_state)
bad_situation_state.when_event_go_to(check_cbt_json, question_state, event_params={})

def extract_abc_information(session: Session):
    """Extract ABC information from the user message and store it as structured data."""
    cbt_struct_data: str = session.get('cbt_struct_data')
    response = llm.extract_abc_information(session.message)
    print(response)
    if cbt_struct_data is None:
        cbt_struct_data = "[]"
    response = llm.combine_abc_information(abc_json=cbt_struct_data, input=json.dumps(response, indent = 4))
    print(response)
    session.set('cbt_struct_data', response)

def question_body(session: Session):
    #session.reply("QUESTION")
    extract_abc_information(session)
    response = llm.belief_questions(session.message)

    session.reply(response)

def check_cbt_information(session: Session, event_params: dict):
    cbt_struct_data: str = session.get('cbt_struct_data')
    cbt_struct_data = json.loads(cbt_struct_data)
    print("check_cbt_information", cbt_struct_data)
    if cbt_struct_data is None:
        return False
    else: 
        for s in cbt_struct_data:
            if "" in s.values():
                return False
    return True

def check_cbt_incomplete(session: Session, event_params: dict):
    return not check_cbt_information(session, event_params)

question_state.set_body(question_body)
question_state.when_intent_matched_go_to(end_cbt_intent, end_cbt_state)
question_state.when_event_go_to(check_cbt_information, recommendation_state, event_params={})
question_state.when_event_go_to(check_cbt_incomplete, incomplete_state, event_params={})


def incomplete_body(session: Session):
    #session.reply("INCOMPLETE")
    extract_abc_information(session)
    cbt_struct_data: str = session.get('cbt_struct_data')
    response = llm.complete_questions(abc_json=cbt_struct_data, input=session.message)
    session.reply(response)


incomplete_state.set_body(incomplete_body)
incomplete_state.when_intent_matched_go_to(end_cbt_intent, end_cbt_state)
incomplete_state.when_event_go_to(check_cbt_information, recommendation_state, event_params={})
incomplete_state.when_event_go_to(check_cbt_incomplete, question_state, event_params={})


def recommendation_body(session: Session):
    #session.reply("RECOMMENDATION")
    cbt_struct_data: str = session.get('cbt_struct_data')
    response = llm.counterarguments_for_fallacies(cbt_struct_data)
    session.reply(response)
    session.reply(bot_messages.end_recommendation.value)
    websocket_platform.reply_options(session, bot_messages.end_options.value)

recommendation_state.set_body(recommendation_body)
recommendation_state.when_intent_matched_go_to(end_cbt_intent,end_cbt_state)
recommendation_state.when_intent_matched_go_to(bad_situation_intent,question_state)


def end_cbt_body(session: Session):
    session.reply(bot_messages.end_cbt.value)

end_cbt_state.set_body(end_cbt_body)
end_cbt_state.go_to(initial_state)



def fallback_body(session: Session):
    #session.reply("FALLBACK")
    extract_abc_information(session)
    session.reply(bot_messages.fallback.value)


bot.set_global_fallback_body(fallback_body)


# RUN APPLICATION

if __name__ == '__main__':
    bot.run()


"""
def fallback_body(session: Session):
    session.reply("Bot is working on your request, please wait a moment...")

    prompt = llm.memory_prompt()
    response = llm.llm_chain(session.message)
    session.reply(response)

    response = llm.belief_questions(session.message)
    print(response)
    session.reply(response)


    response = llm.extract_abc_information(session.message)
    print(response)
    session.reply(json.dumps(response, indent = 4) )
    response = llm.counterarguments_for_fallacies(json.dumps(response, indent = 4) )
    print(response)
    session.reply(response)

bot.set_global_fallback_body(fallback_body)
"""