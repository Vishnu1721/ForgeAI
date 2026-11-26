FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home forge && mkdir /data && chown forge:forge /data
COPY . .
USER forge
ENV FORGE_DB=/data/forge.db
EXPOSE 8000
CMD ["python","-m","uvicorn","app:app","--host","0.0.0.0","--port","8000"]
