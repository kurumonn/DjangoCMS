# KururuCMS の本番イメージ。
#
# 2段構成にしている。ビルドに必要なもの（コンパイラなど）を
# 最終イメージへ持ち込まないため。
# 攻撃者が侵入したときに、その場でコードをビルドする道具を
# 渡さないという意味もある。

# --- 1段目: 依存パッケージを wheel にする -----------------------------------
FROM python:3.12-slim AS builder

# .pyc を書かない / 出力をためこまない。
# 後者はログがリアルタイムで見えなくなるのを防ぐ。
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# psycopg と argon2-cffi のビルドに必要。
RUN apt-get update \
 && apt-get install --no-install-recommends -y build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /wheels
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt

# --- 2段目: 実行用 ----------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

# libpq5 は psycopg の実行時に要る（開発用の libpq-dev は要らない）。
RUN apt-get update \
 && apt-get install --no-install-recommends -y libpq5 \
 && rm -rf /var/lib/apt/lists/*

# root で動かさない。
# コンテナが乗っ取られたとき、root だとホスト側への影響が桁違いに大きくなる。
RUN useradd --create-home --uid 10001 kururu

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
 && rm -rf /wheels

COPY --chown=kururu:kururu . .

# 静的ファイルとアップロードの置き場。
# nginx と共有するので、後で volume がここへマウントされる。
RUN mkdir -p /app/staticfiles /app/media \
 && chown -R kururu:kururu /app/staticfiles /app/media

USER kururu

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
