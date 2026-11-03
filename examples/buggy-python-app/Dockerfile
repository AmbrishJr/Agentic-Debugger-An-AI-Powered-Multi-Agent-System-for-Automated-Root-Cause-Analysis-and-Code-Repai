FROM python:3.12-slim
WORKDIR /fixture
COPY checkout.py test_checkout.py ./
USER 65534:65534
ENV PYTHONDONTWRITEBYTECODE=1
CMD ["python", "-E", "-s", "-B", "-m", "unittest", "-v", "test_checkout"]
