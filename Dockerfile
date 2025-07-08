FROM python:3.10

WORKDIR /app

COPY . /app

RUN pip install --upgrade pip
RUN pip install --no-warn-script-location --no-cache-dir -r requirements.txt

CMD ["python", "crypto_bot.py"]
