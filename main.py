# main.py

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

class WakeWordDetector:
    def __init__(self):
        # Picovoice/Precise は使用せず、キーボード入力でトリガーする実装に変更
        self.chat_gpt_service = ChatGPTService()
        self.listener = InputListener(
            config["silence_threshold"],
            config["silence_duration"]
        )
        # Precise 関連の初期化は削除（またはコメントアウト）

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
            response = self.chat_gpt_service.send_to_chat_gpt(transcription["text"])
            print("ChatGPT response:", response)
            print("Playing response...")
            self.speech.speak(response)
            os.remove(audio_path)
            print("Audio session completed. Press Enter to start again, or type 'exit' to quit.")

if __name__ == "__main__":
    # オプション：silence_detector により環境の無音閾値を計測（必要なら利用）
    detector = ThresholdDetector(5)
    silence_threshold = detector.detect_threshold()

    wake_detector = WakeWordDetector()
    wake_detector.run()