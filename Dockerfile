# Debian Bookworm をベースイメージとして使用
FROM debian:bookworm

# 対話型インストールを無効化
ENV DEBIAN_FRONTEND=noninteractive

# 必要なシステムパッケージをインストール
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    python3-venv \
    portaudio19-dev \
    libsdl2-dev \
    libsdl2-image-dev \
    libsdl2-mixer-dev \
    libsdl2-ttf-dev \
    && rm -rf /var/lib/apt/lists/*

# 作業ディレクトリを設定
WORKDIR /app

# 仮想環境を作成し、以降のコマンドで使用するよう PATH を変更
RUN python3 -m venv venv
ENV PATH="/app/venv/bin:${PATH}"

# 仮想環境内で pip をアップグレード
RUN pip install --upgrade pip

# requirements.txt をコンテナにコピー
COPY requirements.txt .

# 仮想環境内に requirements.txt のパッケージをインストール
RUN pip install --break-system-packages -r requirements.txt

# コンテナ起動時のデフォルトコマンド（必要に応じて変更）
CMD ["python"]