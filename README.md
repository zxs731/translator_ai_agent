# translator_ai_agent
## 该源码包含两套独立的方案：阿里方案、微软方案
### 1.分别对应视频里的中英互译和中日互译的演示。但实际上翻译的语言可以更多。【视频演示】 https://www.bilibili.com/video/BV1BBNmz8Exk/?share_source=copy_web&vd_source=245c190fe77b507d57968a57b3d6f9cf

### 2.阿里方案使用Qwen-Agent方案加ASR（gummy）/TTS（cosyvoice-2），需要注意的是它其实可以直接翻译，而无需智能体。如有需要可修改下面代码可以变为给予ASR的同声翻译机。
### 3.微软方案使用azure-speech方案加tool call，默认即可支持全球语言非常方便。如无需智能体也可去除，降为同声翻译机。


阿里代码片段参考：
<code>
recognizer = TranslationRecognizerRealtime(
            model="gummy-realtime-v1",
            format=ASR_FORMAT,
            sample_rate=ASR_SAMPLE_RATE,
            transcription_enabled=True,
            translation_enabled=False, #此处修改为True即可直接翻译
            callback=asr_callback
        )
</code>
