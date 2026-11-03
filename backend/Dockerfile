FROM python:3.12-slim
WORKDIR /workspace
COPY backend/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock
COPY backend /workspace/backend
COPY examples /workspace/examples
RUN useradd --uid 10001 --create-home app && mkdir -p /workspace/data && chown -R app:app /workspace/data
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
