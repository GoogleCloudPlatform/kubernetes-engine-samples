FROM ubuntu:latest
RUN apt-get update && apt-get install -y socat

# Run a simple SCTP echo server.  This command uses socat to listen for
# incoming SCTP connections on port 50000 and echo back any received data.
# The 'fork' option ensures that a new process is created for each connection.
CMD ["socat", "PIPE", "SCTP-LISTEN:50000,fork"]
