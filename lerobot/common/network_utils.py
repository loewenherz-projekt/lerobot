import ipaddress
import logging
import socket
from typing import Optional


def discover_host(port: int, network_range: str | None = None, timeout: float = 0.3) -> Optional[str]:
    """Scan the network to find a host with an open ``port``.

    Args:
        port: Port number to test on each IP.
        network_range: Optional network range in CIDR notation. If ``None`` the
            function infers the local ``/24`` network from the current hostname.
        timeout: Connection timeout in seconds.

    Returns:
        The IP address of the first host that accepts the connection or ``None``
        if nothing was found.
    """
    if network_range is None:
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
            network_range = ".".join(local_ip.split(".")[:3]) + ".0/24"
        except OSError as err:
            logging.error("Could not determine local IP address: %s", err)
            logging.error("Specify --network-range manually if automatic detection fails.")
            return None

    logging.info("Scanning %s for port %d", network_range, port)
    net = ipaddress.ip_network(network_range, strict=False)
    for ip in net.hosts():
        try:
            with socket.create_connection((str(ip), port), timeout=timeout):
                logging.info("Found follower at %s", ip)
                return str(ip)
        except OSError:
            continue
    logging.error("No host found with open port %d in range %s", port, network_range)
    logging.error("Ensure the follower server is running and reachable from this machine.")
    return None
