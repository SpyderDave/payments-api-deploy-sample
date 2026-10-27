FROM python:3.12-slim AS build
WORKDIR /w
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY --from=build /install /usr/local
WORKDIR /srv
COPY app ./app
# Non-root numeric UID so runAsNonRoot can be verified by the kubelet.
USER 10001
EXPOSE 8000
# One process per pod: scale with replicas (HPA), not workers. Keep-alive > ingress idle timeout avoids 502s.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "75", "--timeout-graceful-shutdown", "30"]
