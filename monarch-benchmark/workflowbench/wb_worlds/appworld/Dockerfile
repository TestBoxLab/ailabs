FROM ghcr.io/stonybrooknlp/appworld@sha256:77d37be71741a740d782c909633845be4a363c5aad8d61530a57f9a1da3c4398
RUN /usr/local/bin/pip --python /opt/venv/bin/python install appworld==0.1.3.post1
ENV PYTHONUTF8=1
COPY server.py /opt/workflowbench/server.py
ENTRYPOINT ["/opt/venv/bin/python", "/opt/workflowbench/server.py"]
CMD []
