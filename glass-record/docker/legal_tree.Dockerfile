FROM glass-record/base:latest
ENV PORT=8080
CMD ["uvicorn", "agents.legal_tree.main:app", "--host", "0.0.0.0", "--port", "8080"]
