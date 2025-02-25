# chat_gpt_service.py

import asyncio
import json
import websockets
import openai
import os
import time

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

    async def send_message(self, message, input_type="text"):
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
        # 応答は複数のストリーミングイベントとして返されるが、ここでは response.text.done イベントを待機して最終的なテキストを取得する例です
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
        elif input_type == "audio" and "audio" in response_json:
            return response_json["audio"]
        else:
            return response_json

    def send_to_chat_gpt(self, message, input_type="text"):
        if self.ws is None:
            self.loop.run_until_complete(self.connect())
        # 同期版のラッパー。send_message() を run_until_complete 経由で呼び出す
        return self.loop.run_until_complete(self.send_message(message, input_type))

    async def close(self):
        if self.ws:
            await self.ws.close()

if __name__ == "__main__":
    # 例として、テキストメッセージを送信
    service = ChatGPTService("You are a helpful assistant.")
    response = service.send_to_chat_gpt("こんにちは、調子はどうですか？")
    print("Assistant:", response)