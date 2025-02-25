#chat_gpt_service.py

import asyncio
import json
import websockets
import openai
import os
import time
import base64
import pyaudio

# 設定読み込み
config = json.load(open("config.json"))
if "openai_org" in config:
    # TODO: The 'openai.organization' option isn't read in the client API.
    # You will need to pass it when you instantiate the client, e.g. 'OpenAI(organization=config["openai_org"])'
    # openai.organization = config["openai_org"]
    pass

class ChatGPTService:
    def __init__(self, prompt="You are a helpful assistant."):
        # 初期システムメッセージは、Realtime API での会話アイテム形式に合わせる
        self.history = [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt
                    }
                ]
            }
        ]
        # Realtime API 用モデル指定（最新のモデルを使用）
        self.model = "gpt-4o-realtime-preview-2024-12-17"
        self.ws = None
        self.session_id = None
        # ここで専用のイベントループを生成し、以降の非同期処理で使用する
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        # Persistent PyAudio instance and output stream for streaming playback
        self.pyaudio_instance = pyaudio.PyAudio()
        self.audio_stream = None

    async def connect(self):
        # ---------------------------
        # まず、セッション作成エンドポイントにPOSTし、エフェメラルトークンを取得する
        # ---------------------------
        try:
            import aiohttp
        except ModuleNotFoundError:
            raise ModuleNotFoundError("aiohttpモジュールが見つかりません。'pip install aiohttp' を実行してください。")
        session_url = "https://api.openai.com/v1/realtime/sessions"
        session_payload = {
            "model": self.model,
            "modalities": ["audio", "text"],
            "instructions": "You are a friendly assistant."
        }
        headers_http = {
            "Authorization": "Bearer " + config['openai_key'],
            "Content-Type": "application/json"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(session_url, headers=headers_http, json=session_payload) as resp:
                session_response = await resp.json()
        # セッションIDおよびエフェメラルトークンを取得
        self.session_id = session_response["id"]
        ephemeral_token = session_response["client_secret"]["value"]

        # ---------------------------
        # 取得したエフェメラルトークンを用いて WebSocket 接続を初期化する
        # ---------------------------
        realtime_api_url = "wss://api.openai.com/v1/realtime?model=" + self.model
        # 最新の websockets ライブラリでは additional_headers を使用する
        ws_headers = {
            "Authorization": "Bearer " + ephemeral_token,
            "OpenAI-Beta": "realtime=v1"
        }
        self.ws = await websockets.connect(realtime_api_url, additional_headers=ws_headers)
        print("Connected to Realtime API.")

        # ---------------------------
        # セッション更新イベントを送信（音声出力設定など）
        # ---------------------------
        session_update = {
            "type": "session.update",
            "session": {
                "modalities": ["audio", "text"],
                "instructions": "You are a friendly assistant.",
                "voice": "alloy",
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": "whisper-1"
                },
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500
                },
                "tools": [],
                "tool_choice": "none",
                "temperature": 0.7,
                "max_response_output_tokens": 200
            }
        }
        await self.ws.send(json.dumps(session_update))
        print("Session updated with audio output settings.")
        
        # Open a persistent PyAudio stream for output audio streaming
        self.audio_stream = self.pyaudio_instance.open(format=pyaudio.paInt16, channels=1, rate=16000, output=True)

    async def send_message(self, message, input_type="text", output_audio=False):
        # ユーザーからのメッセージは、Realtime API の会話アイテム作成イベントとして送信する
        if input_type == "audio":
            # 音声の場合は、message は Base64 エンコード済みの音声データが想定される
            content = [{
                "type": "input_audio",
                "audio": message
            }]
        else:
            content = [{
                "type": "input_text",
                "text": message
            }]

        event_payload = {
            "type": "conversation.item.create",
            "item": {
                "role": "user",
                "content": content
            }
        }
        await self.ws.send(json.dumps(event_payload))
        if output_audio:
            # ★ 修正箇所 ★
            # 音声出力を得るために、response.create イベントを送信する際、指示文で明示的に音声出力も求める
            await self.ws.send(json.dumps({
                "type": "response.create",
                "response": {
                    "modalities": ["audio", "text"],
                    "instructions": "Please answer with both text and audio."
                }
            }))
            full_audio_data = b""
            # 双方向ストリーミング：受信した音声チャンクを即時再生しながらバッファに蓄積する
            while True:
                try:
                    response = await self.ws.recv()
                except websockets.exceptions.ConnectionClosedOK:
                    break
                response_json = json.loads(response)
                if response_json.get("type") == "response.audio.delta":
                    chunk = base64.b64decode(response_json.get("delta"))
                    full_audio_data += chunk
                    # 再生用の persistent stream に書き込み
                    self.audio_stream.write(chunk)
                if response_json.get("type") == "response.audio.done":
                    if full_audio_data:
                        self.history.append({
                            "role": "assistant",
                            "content": [{
                                "type": "audio",
                                "audio": full_audio_data.decode("latin1")
                            }]
                        })
                    break
            # 返却値は空にする（すでにリアルタイム再生済み）
            return b""
        else:
            response = await self.ws.recv()
            response_json = json.loads(response)
            if response_json.get("type") == "response.text.done":
                assistant_text = response_json.get("text", "")
                # 会話履歴に追加
                self.history.append({
                    "role": "assistant",
                    "content": [{
                        "type": "text",
                        "text": assistant_text
                    }]
                })
                return assistant_text
            else:
                return response_json

    def send_to_chat_gpt(self, message, input_type="text", output_audio=False):
        if self.ws is None:
            self.loop.run_until_complete(self.connect())
        # 同期版のラッパー。send_message() を run_until_complete 経由で呼び出す
        return self.loop.run_until_complete(self.send_message(message, input_type, output_audio))

    async def close(self):
        if self.ws:
            await self.ws.close()
        if self.audio_stream:
            self.audio_stream.stop_stream()
            self.audio_stream.close()
        self.pyaudio_instance.terminate()

if __name__ == "__main__":
    # 例として、テキストメッセージを送信
    service = ChatGPTService("You are a helpful assistant.")
    response = service.send_to_chat_gpt("こんにちは、調子はどうですか？")
    print("Assistant:", response)