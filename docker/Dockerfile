FROM python:3.11-slim

WORKDIR /srv/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data ./data

RUN mkdir -p data/state data/reservations

EXPOSE 8000 8010

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
