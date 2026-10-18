FROM python:3.12-slim
WORKDIR /srv/backend
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV DOLIL_DATA=/srv/data/runtime
EXPOSE 8000
CMD ["sh", "-c", "[ -f $DOLIL_DATA/dolil.db ] || python -m app.seed; uvicorn app.main:app --host 0.0.0.0 --port 8000"]
