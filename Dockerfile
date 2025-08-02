FROM python:3.14.0rc1-slim-bookworm

WORKDIR /app

COPY . /app

RUN pip install --upgrade pip
RUN pip install --no-warn-script-location --no-cache-dir -r requirements.txt

CMD ["python", "crypto_bot.py"]
RUN pip install flask
