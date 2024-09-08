FROM flant/shell-operator
RUN apk update && \
    apk add --no-cache py3-requests
COPY main.py /hooks