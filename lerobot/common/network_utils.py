import ipaddress
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
        except OSError:
            return None

    net = ipaddress.ip_network(network_range, strict=False)
    for ip in net.hosts():
        try:
            with socket.create_connection((str(ip), port), timeout=timeout):
                return str(ip)
        except OSError:
            continue
    return None
