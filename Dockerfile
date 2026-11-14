FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY membrane ./membrane
COPY scripts ./scripts
ENV PORT=8000
EXPOSE 8000
# MONGODB_URI, LLM_PROVIDER and LLM_API_KEY are supplied as environment variables at run time.
CMD ["sh", "-c", "uvicorn membrane.app:app --host 0.0.0.0 --port ${PORT}"]
