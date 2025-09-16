FROM python:3.10

WORKDIR /app

COPY . /app

RUN pip install --upgrade pip
RUN pip install --no-warn-script-location --no-cache-dir -r requirements.txt

# Flask ko requirements.txt me add kar lena
EXPOSE 8080

CMD ["python", "crypto_bot.py"]
