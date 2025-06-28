
import os  
from dotenv import load_dotenv  
import io  
import azure.cognitiveservices.speech as speechsdk  
from openai import OpenAI
import time  
import datetime  
import threading  
import json, ast  
from tools import *
import requests  
from io import BytesIO  
import tempfile  
import numpy as np 
  
load_dotenv("voice-azure.env")  
from openai import AzureOpenAI



# 使用基于密钥的身份验证初始化 Azure OpenAI 客户端
client = AzureOpenAI(
    azure_endpoint=os.getenv("ENDPOINT_URL", ""),
    api_key=os.getenv("AZURE_OPENAI_API_KEY", "REPLACE_WITH_YOUR_KEY_VALUE_HERE"),
    api_version="2025-01-01-preview",
)

Azure_speech_key = os.environ["Azure_speech_key"]  
Azure_speech_region = os.environ["Azure_speech_region"]  
Azure_speech_speaker = os.environ["Azure_speech_speaker"]  
WakeupWord = os.environ["WakeupWord"]  
WakeupModelFile = os.environ["WakeupModelFile"]  

messages = []  

# Set up Azure Speech-to-Text and Text-to-Speech credentials  
speech_key = Azure_speech_key  
service_region = Azure_speech_region  
speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)  
# Set up Azure Text-to-Speech language  
speech_config.speech_synthesis_language = "zh-CN"  
# Set up Azure Speech-to-Text language recognition  
speech_config.speech_recognition_language = "zh-CN"  
lang = "zh-CN"  
# Set up the voice configuration  
speech_config.speech_synthesis_voice_name = Azure_speech_speaker  
speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)  
connection = speechsdk.Connection.from_speech_synthesizer(speech_synthesizer)  
connection.open(True)  
# Creates an instance of a keyword recognition model. Update this to  
# point to the location of your keyword recognition model.  
model = speechsdk.KeywordRecognitionModel(WakeupModelFile)  
# The phrase your keyword recognition model triggers on.  
keyword = WakeupWord  
# Set up the audio configuration  
audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)  
# Create a speech recognizer and start the recognition  
#speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)  
auto_detect_source_language_config = speechsdk.languageconfig.AutoDetectSourceLanguageConfig(languages=["ja-JP", "zh-CN"])  
speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config,  
                                               auto_detect_source_language_config=auto_detect_source_language_config)  
unknownCount = 0  
sysmesg = {"role": "system", "content": os.environ["sysprompt_zh-CN"]}  
tts_sentence_end = [ ".", "!", "?", ";", "。", "！", "？", "；", "\n" ]


isListenning=False
def display_text(s):
    print(s)
def speech_to_text():  
    global unknownCount  
    global lang,isListenning  
    print("Please say...")  
    result = speech_recognizer.recognize_once_async().get()  
    if result.reason == speechsdk.ResultReason.RecognizedSpeech:  
        unknownCount = 0  
        isListenning=False
        return result.text  
    elif result.reason == speechsdk.ResultReason.NoMatch:  
        isListenning=False
        unknownCount += 1  
        error = os.environ["sorry_" + lang]  
        text_to_speech(error)  
        return '...'  
    elif result.reason == speechsdk.ResultReason.Canceled:  
        isListenning=False
        return "speech recognizer canceled." 
    

def getVoiceSpeed():  
    return 17  
  
def text_to_speech(text, _lang=None):  
    global lang  
    try:  
        result = buildSpeech(text).get()  
        #result = speech_synthesizer.speak_ssml_async(ssml_text).get()  
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:  
            print("Text-to-speech conversion successful.")  
            return "Done."  
        else:  
            print(f"Error synthesizing audio: {result}")  
            return "Failed."  
    except Exception as ex:  
        print(f"Error synthesizing audio: {ex}")  
        return "Error occured!"  
target_lang=lang        
def buildSpeech(text, _lang=None):
    if _lang:
        l=_lang
    else:
        l=lang
    voice_lang = lang  
    voice_name = "zh-CN-XiaoxiaoMultilingualNeural"  
    ssml_text = f'''  
        <speak xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="http://www.w3.org/2001/mstts" xmlns:emo="http://www.w3.org/2009/10/emotionml" version="1.0" xml:lang="{l}"><voice name="{voice_name}"><lang xml:lang="{l}"><prosody rate="{getVoiceSpeed()}%">{text.replace('*', ' ').replace('#', ' ')}</prosody></lang></voice></speak>  
    '''  
    print(f"{voice_name} {voice_lang}!")  
    return speech_synthesizer.speak_ssml_async(ssml_text)
  
def generate_text(prompt):  
    global messages  
    messages.append({"role": "user", "content": prompt+getThinkingMode()})  
    #tools = getTools()  
    collected_messages = []
    last_tts_request = None

    split=True
    
    
    response_gen = client.chat.completions.create(
        model=os.environ["model"],
        messages=[sysmesg]+messages[-20:],
        tools=getTools(),
        stream=True
    )#gpt.chat_stream(prompt)
    # 循环接收返回的message
    while True:
        result=''
        function_list=[]
        index=0
        for chunk in response_gen:
            if chunk and len(chunk.choices) > 0 and chunk.choices[0].delta is not None:
                delta = chunk.choices[0].delta
                chunk_message =  delta.content  # 抽取流式message里的内容
          
                if chunk_message is not None and chunk_message!='':
                    collected_messages.append(chunk_message)  # 收集保存message
                    result=result+chunk_message
                    #print(chunk_message,end="|")
                    if chunk_message in tts_sentence_end and split: # 发现分段标记：句子结束
                        text = ''.join(collected_messages).strip() # 构建句子
                        if len(text)>500 or "</think>" in text: #如果这句足够长，后面不再分段朗读了
                            split=False
                        elif len(text)<6: #如果这句太短了，不单独朗读，并入后面
                            continue
                        
                        
                        if text != '': # 如果句子里只有 \n or space则跳过朗读
                            print(f"Speech synthesized to speaker for: {text}")
                            #text=text.replace("<think>","让我先来思考一下：")
                            #text=text.replace("</think>","嗯，我想好了，下面是我的回答。")
                            last_tts_request = buildSpeech(text,target_lang)  # 调用语音合成
                            #last_tts_request = speech_synthesizer.speak_text_async(text)
                            collected_messages.clear()
                            
                if delta.tool_calls: 
                    for tool_call in delta.tool_calls:
                        if len(function_list) < tool_call.index + 1:  
                            function_list.append({'name': '', 'args': '', 'id': tool_call.id})  
                        if tool_call and tool_call.function.name:  
                            function_list[tool_call.index]['name'] += tool_call.function.name  
                        if tool_call and tool_call.function.arguments:  
                            function_list[tool_call.index]['args'] += tool_call.function.arguments  
                             
                 
        print(function_list)
        
        if len(function_list)>0:
            findex=0
            tool_calls=[]
            temp_messages=[]
            for func in function_list:
                function_name = func["name"]
                print(function_name)
                function_args = func["args"]
                toolid=func["id"]
                if function_name !='':
                    print(f'⏳Call {function_name}...')
                    function_to_call = globals()[function_name]
                    function_args = json.loads(function_args)
                    print(f'⏳Call params: {function_args}')
                    
                    function_response = function_to_call(**function_args)
                    print(f'⏳Call internal function done! ')
                    print("执行结果：")
                    print(function_response)
                    tool_calls.append({"id":toolid,"function":{"arguments":func["args"], "name":function_name}, "type":"function","index":findex})
                    
                    temp_messages.append(
                        {
                        "tool_call_id": toolid,
                        "role": "tool",
                        "name": function_name,
                        "content": function_response,
                        }
                    )
                    
                    findex+=1
                    
            messages.append({
                        "role":"assistant",
                        "content":'',
                        "tool_calls":tool_calls,
                    })
            for m in temp_messages:
                messages.append(m)
                
            response_gen = client.chat.completions.create(
                model=os.environ["model"],
                messages=messages,
                tools=getTools(),
                stream=True
            ) 
        else:
            if result!='':        
                messages.append({"role": "assistant", "content": result})
            
            if len(collected_messages)>0:
                text = ''.join(collected_messages).strip() 
                if text != '': 
                    print(f"Speech synthesized to speaker for: {text}")
                    last_tts_request = buildSpeech(text,target_lang)
                    collected_messages.clear()
        
            
            if last_tts_request:
                last_tts_request.get()   
                
            break
           
    return result
  
def Get_Chat_Deployment():  
    deploymentModel = os.environ["Azure_OPENAI_Chat_API_Deployment"]  
    return deploymentModel  
  

def recognized_cb(evt):  
    result = evt.result  
    if result.reason == speechsdk.ResultReason.RecognizedKeyword:  
        print("RECOGNIZED KEYWORD: {}".format(result.text))  
    global done  
    done = True  

def canceled_cb(evt):  
    result = evt.result  
    if result.reason == speechsdk.ResultReason.Canceled:  
        print('CANCELED: {}'.format(result.cancellation_details.reason))  
    global done  
    done = True  
   
def start_recognition():  
    global unknownCount ,isListenning ,playing
    while True:  
        keyword_recognizer = speechsdk.KeywordRecognizer()  
        keyword_recognizer.recognized.connect(recognized_cb)  
        keyword_recognizer.canceled.connect(canceled_cb) 
        first=os.environ["welcome_" + lang]
        display_text(first) 
        if getPlayerStatus()!='playing':
            text_to_speech(first)  
        isListenning=True
        result_future = keyword_recognizer.recognize_once_async(model)  
        while True:  
            result = result_future.get()
            # Read result audio (incl. the keyword).
            if result.reason == speechsdk.ResultReason.RecognizedKeyword:
                print("Keyword recognized")
                isListenning=False
                if getPlayerStatus()=='playing':
                    pauseplay() #被唤醒后，如果有音乐播放则暂停播放
                break
            time.sleep(0.1)  
            
        display_text("很高兴为您服务，我在听请讲。")  
        text_to_speech("很高兴为您服务，我在听请讲。")  
        
          
        while unknownCount < 2:
            isListenning=True
            user_input = speech_to_text()
            if user_input=='...':
                continue
            print(f"You: {user_input}")  
            
            display_text(f"You: {user_input}")  
            response = generate_text(user_input)
            print(getPlayerStatus())
            if getPlayerStatus()=='playing':
                break
            
            #text_to_speech(f"你说的是：{user_input}")  
            
          
        bye_text = os.environ["bye_" + lang]  
        display_text(bye_text) 
        if getPlayerStatus()!='playing':
            text_to_speech(bye_text)  
        
        unknownCount = 0  
        time.sleep(0.1)  

def QuitTranlationMode():
    global sysmesg, target_lang
    target_lang="cn-ZH"
    sysmesg["content"] = f'''You're a AI assistant。/no think'''
    return "Translation meode has been quit. "
def EnterTranlationMode(target_language_code):
    global sysmesg, target_lang
    sysmesg["content"]  = f'''You're a translator, you MUST translate my input to language ({target_language_code})。Note: You should translate my question/sentence, NOT answer my questions! Don't include any comments or explanation. '''
    target_lang = target_language_code
    return f"Translation mode is set to {target_language_code}. " 

if __name__ == "__main__":
    start_recognition()