# Trusted infrastructure image: never build a repository-provided Dockerfile.
FROM python:3.12-slim
COPY bootstrap.py /opt/autorca/bootstrap.py
RUN chmod 0555 /opt/autorca/bootstrap.py
USER 65534:65534
WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/python", "-I", "-B", "/opt/autorca/bootstrap.py"]
