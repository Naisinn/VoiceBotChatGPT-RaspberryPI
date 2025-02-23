# chat_gpt_service.py

import json
import asyncio
import websockets
import openai
import os
import time

# 設定読み込み
config = json.load(open("config.json"))
openai.api_key = config["openai_key"]
if "openai_org" in config:
    openai.organization = config["openai_org"]

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
        self.ws = await websockets.connect(realtime_api_url, extra_headers=headers)
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

    async def close(self):
        if self.ws:
            await self.ws.close()