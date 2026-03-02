ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ENV PORT=8080
CMD ["uvicorn", "agents.researcher.main:app", "--host", "0.0.0.0", "--port", "8080"]
