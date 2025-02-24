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
        # Realtime API 用モデル指定
        self.model = "gpt-4o-mini-realtime-preview-2024-12-17"
        self.ws = None

    async def connect(self):
        # Realtime API の WebSocket エンドポイント（最新のドキュメントに合わせて変更してください）
        realtime_api_url = "wss://api.openai.com/v1/realtime"
        headers = {
            "Authorization": f"Bearer {config['openai_key']}",
            "Content-Type": "application/json"
        }
        # extra_headers をリスト形式に変換して渡す
        headers_list = list(headers.items())
        self.ws = await websockets.connect(realtime_api_url, extra_headers=headers_list)
        print("Connected to Realtime API.")

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
            asyncio.run(self.connect())
        # 同期版のラッパー。send_message() を asyncio.run() 経由で呼び出す
        return asyncio.run(self.send_message(message, input_type))

    async def close(self):
        if self.ws:
            await self.ws.close()