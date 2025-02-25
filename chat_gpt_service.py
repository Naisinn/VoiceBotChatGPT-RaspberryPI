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
        # Realtime API 用モデル指定
        self.model = "gpt-4o-mini-realtime-preview-2024-12-17"
        self.ws = None
        # ここで専用のイベントループを生成し、以降の非同期処理で使用する
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

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
        # ユーザーの発言を表す会話アイテム作成イベント
        request = {
            "type": "conversation.item.create",
            "item": {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": message}
                ]
            }
        }
        await self.ws.send(json.dumps(request))
        # アシスタントからの応答を促すため、response.create イベントを送信
        trigger = {
            "type": "response.create",
            "response": {
                "modalities": ["text"],
                "instructions": "Please assist the user."
            }
        }
        await self.ws.send(json.dumps(trigger))
        # 応答イベントを受信する
        response = await self.ws.recv()
        response_json = json.loads(response)
        # 応答形式は API の仕様により変動するため、ここでは仮に "message" フィールドからテキストを抽出
        assistant_msg = response_json.get("message", "")
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