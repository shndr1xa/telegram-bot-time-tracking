FROM python:3.14-alpine

WORKDIR /app

COPY requirements.txt /app/

RUN pip install -r requirements.txt

COPY bot.py bot.py

COPY .env .env

ENTRYPOINT [ "python", "bot.py" ]