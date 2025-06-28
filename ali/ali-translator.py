import json
import pyaudio
import dashscope
from dashscope.audio.asr import TranslationRecognizerRealtime, TranslationRecognizerCallback,TranscriptionResult,TranslationResult
from dashscope.audio.tts_v2 import SpeechSynthesizer, ResultCallback,AudioFormat
from dashscope import Generation
from qwen_agent.agents import Assistant
from http import HTTPStatus
import threading
import time
import os
import json5
from dotenv import load_dotenv
load_dotenv("ali.env")
from qwen_agent.tools.base import BaseTool, register_tool


@register_tool('enter_translator_mode')
class EnterTranlationMode(BaseTool):
    description = 'enter translator mode'
    parameters = [{
        'name': 'target_language',
        'type': 'string',
        'description': 'the target language you want to translate to, e.g. "English", "Chinese", "French", etc. You should ask user to input the target language if user does not mention it.',
        'required': True
    }]

    def call(self, params: str, **kwargs) -> str:
        global system_instruction
        print(" EnterTranlationMode params:",params)
        prompt = json5.loads(params)['target_language']
        system_instruction = f'''You're a translator, you MUST translate my input to language {prompt}。Note: You should translate my question/sentence, NOT answer my questions! Don't include any comments or explanation. /no think'''
        bot = Assistant(llm=llm_cfg,
                system_message=system_instruction,
                function_list=tools)
        return f'Translator mode has been entered, I will translate your question to {prompt} language.'

@register_tool('quit_translator_mode')
class QuitTranlationMode(BaseTool):
    description = 'quit translator mode'
    parameters = []

    def call(self, params: str, **kwargs) -> str:
        global system_instruction,bot
        print(" QuitTranlationMode params:",params)
        system_instruction = f'''You're a AI assistant。/no think'''
        bot = Assistant(llm=llm_cfg,
                system_message=system_instruction,
                function_list=tools)
        return f'Translator mode has been quit.'
    
# 设置 DashScope API Key
dashscope.api_key = os.environ["key"]
llm_cfg = {
    'api_key': os.environ["key"],
    'model':'qwen-plus-latest',
    'model_server': 'dashscope',  # base_url, also known as api_base
    'generate_cfg': {
        'top_p': 0.8,
        'thought_in_content': False,
    }
}
system_instruction = '''You're a AI assistant. /no think'''
    
tools = ['enter_translator_mode','quit_translator_mode'] # `code_interpreter` is a built-in tool for executing code.
bot = Assistant(llm=llm_cfg,
                system_message=system_instruction,
                function_list=tools)
# 音频参数
ASR_FORMAT = "pcm"
ASR_SAMPLE_RATE = 16000
TTS_FORMAT = AudioFormat.PCM_22050HZ_MONO_16BIT
TTS_RATE = 22050

# 全局状态变量
#mic = None
#stream = None
asr_callback = None
recognizer = None
user_input_ready = threading.Event()
user_input_text = ""

# 回调类 - ASR
class ASRCallback(TranslationRecognizerCallback):
    def __init__(self):
        self.transcription_buffer = ""
        self.timer = None
        self.is_listening = True
        self.mic=None
        self.stream=None

    def on_open(self):
        #global mic, stream
        self.mic = pyaudio.PyAudio()
        self.stream = self.mic.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=ASR_SAMPLE_RATE,
            input=True
        )
        print("ASR: 语音识别已启动，请开始说话...")

    def on_close(self):
        #global mic, stream
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream=None
        if self.mic:
            self.mic.terminate()
            self.mic=None
        print("ASR: 语音识别已关闭。")

    def on_event(self, request_id, transcription_result: TranscriptionResult, translation_result: TranslationResult, usage):
        global user_input_text, user_input_ready

        if transcription_result:
            current_text = transcription_result.text.strip()
            if current_text:
                self.update_buffer(current_text)

    def update_buffer(self, text):
        global user_input_text
        self.transcription_buffer = text
        self.reset_timer()

    def reset_timer(self):
        if self.timer:
            self.timer.cancel()
        self.timer = threading.Timer(1, self.on_timeout)
        self.timer.start()

    def on_timeout(self):
        global user_input_text, user_input_ready
        user_input_text = self.transcription_buffer.strip()
        if user_input_text:
            print("检测到停顿，用户输入完成：", user_input_text)
            self.is_listening = False
            user_input_ready.set()

# 回调类 - TTS
class TTSCallback(ResultCallback):
    def __init__(self):
        self._player = None
        self._stream = None

    def on_open(self):
        self._player = pyaudio.PyAudio()
        self._stream = self._player.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=TTS_RATE,
            output=True
        )
        print("TTS: 语音合成已启动。")

    def on_close(self):
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream=None
        if self._player:
            self._player.terminate()
            self._player=None
        print("TTS: 语音合成已关闭。")

    def on_data(self, data: bytes):
        if self._stream:
            self._stream.write(data)




messages=[]       
# 处理用户输入，调用大模型生成回复
def process_input(user_input):
    global messages
    print("处理用户输入：", user_input)
    messages += [{"role": "user", "content": user_input}]
    
    

    # 初始化 TTS
    tts_callback = TTSCallback()
    synthesizer = SpeechSynthesizer(
        model="cosyvoice-v2",
        voice="longxiaochun_v2",
        format=TTS_FORMAT,
        callback=tts_callback
    )
    index=0
    reply = ""
    for response in bot.run(messages):
        reply = sentence = response[-1]["content"]
        s=sentence[index:]
        print(s,end="",flush=True)
        synthesizer.streaming_call(s) 
        index=len(sentence)


    

    messages += [{"role": "assistant", "content": reply}]
    print("\n回复内容：", reply)
    synthesizer.streaming_complete()  # 仍需调用
    #print("1111111")
    #tts_callback.on_close()
    print('回复播放完成，重新进入监听状态。')

# 主循环：持续监听并处理语音输入
def run_assistant():
    # 初始化 TTS
    tts_callback = TTSCallback()
    synthesizer = SpeechSynthesizer(
        model="cosyvoice-v2",
        voice="longxiaochun_v2",
        format=TTS_FORMAT,
        callback=tts_callback
    )
    synthesizer.streaming_call("你好啊，我是小新，我们聊聊吧。")
    synthesizer.streaming_complete() 

    while True:
        print("等待用户输入...")
        global asr_callback, recognizer
        # 重置旧的 ASR 实例
        if asr_callback:
            asr_callback = None
        if recognizer:
            recognizer = None

        asr_callback = ASRCallback()
        recognizer = TranslationRecognizerRealtime(
            model="gummy-realtime-v1",
            format=ASR_FORMAT,
            sample_rate=ASR_SAMPLE_RATE,
            transcription_enabled=True,
            translation_enabled=False,
            callback=asr_callback
        )
        recognizer.start()
        asr_callback.is_listening = True

        while asr_callback.is_listening:
            if asr_callback.stream:
                try:
                    data = asr_callback.stream.read(3200, exception_on_overflow=False)
                    recognizer.send_audio_frame(data)
                except Exception as e:
                    print("录音出错：", e)
                    break
            else:
                break

        recognizer.stop()
        #asr_callback.on_close()

        if user_input_ready.is_set():
            process_input(user_input_text)
            user_input_ready.clear()

# 启动语音助手
if __name__ == "__main__":
    user_input_ready.clear()
    run_assistant()
