# input_listener.py

import time
import audioop
import pyaudio
import boto3
import wave
import uuid
import os


class InputListener:
    def __init__(self, silence_threshold=75, silence_duration=1.5):
        self.chunk = 1024
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 16000
        self.silence_threshold = silence_threshold
        self.silence_duration = silence_duration
        self.audio = pyaudio.PyAudio()
        self.frames = []

    def start(self):
        # self.audio が有効かチェック。既に terminate されている場合は再初期化する
        try:
            self.audio.get_device_count()
        except Exception:
            self.audio = pyaudio.PyAudio()
        
        # 自動的に利用可能な入力デバイスを検索
        available_devices = []
        for i in range(self.audio.get_device_count()):
            dev_info = self.audio.get_device_info_by_index(i)
            if dev_info.get("maxInputChannels", 0) > 0:
                available_devices.append((i, dev_info["name"]))
        if not available_devices:
            print("利用可能な入力デバイスが見つかりません。")
            exit(1)
        elif len(available_devices) == 1:
            device_index = available_devices[0][0]
            print(f"唯一の入力デバイス '{available_devices[0][1]}' (index: {device_index}) を使用します。")
        else:
            print("利用可能な入力デバイスが複数見つかりました:")
            for idx, (dev_index, dev_name) in enumerate(available_devices):
                print(f"{idx}: {dev_name} (index: {dev_index})")
            while True:
                try:
                    selection = int(input("使用するデバイスの番号を入力してください: "))
                    if 0 <= selection < len(available_devices):
                        device_index = available_devices[selection][0]
                        break
                    else:
                        print("無効な番号です。もう一度入力してください。")
                except ValueError:
                    print("数値を入力してください。")
            print(f"選択されたデバイス: '{available_devices[selection][1]}' (index: {device_index})")
        
        self.stream = self.audio.open(
            format=self.format,
            channels=self.channels,
            rate=self.rate,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=self.chunk,
        )

    def stop(self):
        self.stream.stop_stream()
        self.stream.close()
        self.audio.terminate()

    def save_audio_to_file(self, audio_data):
        # Generate a random file name
        file_name = str(uuid.uuid4()) + ".wav"
        file_path = os.path.join("", file_name)  # /path/to/save/directory', file_name)

        # if the file already exists, delete it
        if os.path.exists(file_path):
            os.remove(file_path)

        # Save the audio data to the file
        wf = wave.open(file_path, "wb")
        wf.setnchannels(self.channels)
        wf.setsampwidth(self.audio.get_sample_size(self.format))
        wf.setframerate(self.rate)
        wf.writeframes(audio_data)
        wf.close()

        return file_path

    def listen(self):
        self.start()
        silence_start_time = None
        print("Start recording...")
        while True:
            data = self.stream.read(self.chunk)
            self.frames.append(data)
            rms = audioop.rms(data, 2)
            print(f"RMS: {rms}")  # Debugging print
            if rms < self.silence_threshold:
                if silence_start_time is None:
                    silence_start_time = time.time()
                elif time.time() - silence_start_time > self.silence_duration:
                    print("Silence detected, stop recording")
                    break
            else:
                silence_start_time = None
        self.stop()

        # Save the audio data to a file and return the file path
        audio_data = b"".join(self.frames)
        file_path = self.save_audio_to_file(audio_data)

        # Clear out self.frames
        self.frames = []

        return file_path

    def transcribe(self, audio_data):
        client = boto3.client("transcribe")
        response = client.start_transcription_job(
            TranscriptionJobName="MyTranscriptionJob",
            Media={"MediaFileUri": audio_data},
            MediaFormat="wav",
            LanguageCode="en-US",
        )
        while True:
            status = client.get_transcription_job(
                TranscriptionJobName="MyTranscriptionJob"
            )
            if status["TranscriptionJob"]["TranscriptionJobStatus"] in [
                "COMPLETED",
                "FAILED",
            ]:
                break
            print("Not ready yet...")
            time.sleep(5)
        print(status)