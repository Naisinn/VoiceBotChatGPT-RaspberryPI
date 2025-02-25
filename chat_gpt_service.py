# chat_gpt_service.py

import asyncio
# まず、BaseEventLoop.create_connection を monkey-patch して extra_headers を無視する
_original_create_connection = asyncio.BaseEventLoop.create_connection

def _create_connection_with_extra_headers(self, protocol_factory, host=None, port=None, **kwargs):
    # extra_headers キーワードを削除してから呼び出す
    kwargs.pop("extra_headers", None)
    return _original_create_connection(self, protocol_factory, host, port, **kwargs)

asyncio.BaseEventLoop.create_connection = _create_connection_with_extra_headers

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
        self.history = [{"role": "system", "content": prompt}]
        # Realtime API 用モデル指定（新しい接続例に合わせて更新）
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
        import aiohttp
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
        ws_headers = [
            "Authorization: Bearer " + ephemeral_token,
            "OpenAI-Beta: realtime=v1"
        ]
        self.ws = await websockets.connect(realtime_api_url, extra_headers=ws_headers)
        print("Connected to Realtime API.")
        # セッション更新イベントを送信（音声出力設定など）
        session_update = {
            "type": "session.update",
            "session": {
                "modalities": ["audio", "text"],
                "instructions": "You are a friendly assistant.",
                "voice": "alloy",
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                    "create_response": True
                },
                "temperature": 0.7,
                "max_response_output_tokens": 200
            }
        }
        await self.ws.send(json.dumps(session_update))
        print("Session updated with audio output settings.")

    async def send_message(self, message, input_type="text"):
        # ユーザー入力を履歴に追加
        self.history.append({"role": "user", "content": message, "input_type": input_type})
        request = {
            "model": self.model,
            "messages": self.history,
            "input_type": input_type
        }
        await self.ws.send(json.dumps(request))
        response = await self.ws.recv()
        response_json = json.loads(response)
        # 音声入力の場合は "audio" フィールドに応答が入る（Base64 文字列）
        if input_type == "audio" and "audio" in response_json:
            return response_json["audio"]
        else:
            assistant_msg = response_json.get("choices", [{}])[0].get("message", {}).get("content", "")
            self.history.append({"role": "assistant", "content": assistant_msg})
            return assistant_msg

    def send_to_chat_gpt(self, message, input_type="text"):
        if self.ws is None:
            self.loop.run_until_complete(self.connect())
        # 同期版のラッパー。send_message() を self.loop.run_until_complete 経由で呼び出す
        return self.loop.run_until_complete(self.send_message(message, input_type))

    async def close(self):
        if self.ws:
            await self.ws.close()