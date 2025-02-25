#main.py

import json
from chat_gpt_service import ChatGPTService
from input_listener import InputListener
import os
import openai
from openai import OpenAI
from silence_detector import ThresholdDetector
# from precise_listener import PreciseListener  # Precise 関連は使用しないのでコメントアウト

config = json.load(open("config.json"))
# クライアントインスタンスを生成（グローバル設定ではなくこちらを使用）
client_instance = OpenAI(api_key=config["openai_key"])

if "openai_org" in config:
    # 組織情報は新しいクライアントでは明示的に渡す必要がありますが、必要なければここは pass してください
    pass

def play_audio(audio_data):
    if audio_data is None:
        print("音声データが返ってこなかったため、再生をスキップします。")
        return
    import pyaudio
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, output=True)
    stream.write(audio_data)
    stream.stop_stream()
    stream.close()
    p.terminate()

class WakeWordDetector:
    def __init__(self):
        # Picovoice/Precise は使用せず、キーボード入力でトリガーする実装に変更
        # 以下のインスタンス生成を削除（イベントループの不整合を避けるため）
        # self.chat_gpt_service = ChatGPTService()
        self.listener = InputListener(
            config["silence_threshold"],
            config["silence_duration"]
        )
        # TTS機能はRealtime APIの返答で音声データが返されるため、外部TTSの呼び出しは不要です。
        # そのため、self.speech に関する初期化は削除します。

    def run(self):
        print("Precise wake word detection is disabled.")
        print("Press Enter to start audio input (type 'exit' to quit).")
        while True:
            user_input = input(">> ")
            if user_input.strip().lower() == "exit":
                break
            print("Starting audio recording...")
            audio_path = self.listener.listen()
            print("Transcribing...")
            with open(audio_path, "rb") as audio_file:
                # クライアントインスタンスを利用して音声文字起こしを実行
                transcription = client_instance.audio.transcriptions.create(
                    file=audio_file,
                    model="whisper-1"
                )
            print("Transcript:", transcription)
            print("Sending to ChatGPT...")
            # イベントループの不整合を避けるため、直前に ChatGPTService のインスタンスを生成
            chat_gpt_service = ChatGPTService()
            # transcription はオブジェクトなので、属性 text を使用して文字列を取得
            # 双方向ストリーミングの場合、送信後はAPI側から連続して音声チャンクが再生されます。
            response = chat_gpt_service.send_to_chat_gpt(transcription.text, output_audio=True)
            print("ChatGPT response received.")
            # ※音声はリアルタイム再生済みのため、再生呼び出しは削除しています。
            os.remove(audio_path)
            print("Audio session completed. Press Enter to start again, or type 'exit' to quit.")

if __name__ == "__main__":
    # オプション：silence_detector により環境の無音閾値を計測（必要なら利用）
    detector = ThresholdDetector(5)
    silence_threshold = detector.detect_threshold()

    wake_detector = WakeWordDetector()
    wake_detector.run()



import time
import audioop
import pyaudio

class ThresholdDetector:
    def __init__(self, sample_duration=5):
        self.chunk = 1024
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 16000
        self.sample_duration = sample_duration
        self.audio = pyaudio.PyAudio()

    def start(self):
        self.stream = self.audio.open(
            format=self.format,
            channels=self.channels,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk,
        )

    def stop(self):
        self.stream.stop_stream()
        self.stream.close()
        self.audio.terminate()

    def detect_threshold(self):
        self.start()
        rms_values = []
        start_time = time.time()
        print("Start detecting threshold...")
        while True:
            data = self.stream.read(self.chunk)
            rms = audioop.rms(data, 2)
            print(f"RMS value: {rms}")
            rms_values.append(rms)
            if time.time() - start_time > self.sample_duration:
                print("Sample duration completed, stop detecting")
                break
        self.stop()

        # Calculate the average RMS value as the silence threshold
        average_rms = sum(rms_values) / len(rms_values)
        print(f"The average RMS value is {average_rms}")
        return average_rms

if __name__ == "__main__":
    detector = ThresholdDetector()
    silence_threshold = detector.detect_threshold()