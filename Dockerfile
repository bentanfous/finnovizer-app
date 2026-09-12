# Alternative au buildpack Nixpacks : build reproductible.
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV INNOVIZER_RAW_DIR=/data/raw_uploads
ENV INNOVIZER_DERIVED_DIR=/data/derived
EXPOSE 8000
CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
