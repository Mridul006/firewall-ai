# Isolated sandbox image for testing candidate firewall rules against replayed
# traffic before anything reaches the live firewall. Never connected to the
# real network — tester.py always runs containers from this image with
# --network none.
FROM ubuntu:22.04

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        iptables \
        tcpreplay \
        iproute2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /sandbox

# Idles so tester.py can exec iptables/tcpreplay commands into it on demand.
CMD ["sleep", "infinity"]
