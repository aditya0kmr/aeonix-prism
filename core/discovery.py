import socket
from zeroconf import IPVersion, ServiceInfo, Zeroconf
from typing import Optional

class AeonixDiscoveryService:
    def __init__(self, port: int = 8080, name: str = "AeonixCore"):
        self.port = port
        self.name = name
        self.zeroconf: Optional[Zeroconf] = None
        self.info: Optional[ServiceInfo] = None

    def get_local_ip(self) -> str:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = "127.0.0.1"
        finally:
            s.close()
        return ip

    def start(self) -> bool:
        try:
            local_ip = self.get_local_ip()
            desc = {"version": "2.0", "vendor": "AeonixPrism", "surface": "CoreMind"}
            
            self.info = ServiceInfo(
                type_="_aeonix._tcp.local.",
                name=f"{self.name}._aeonix._tcp.local.",
                addresses=[socket.inet_aton(local_ip)],
                port=self.port,
                properties=desc,
                server="aeonix-core.local."
            )
            self.zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
            self.zeroconf.register_service(self.info)
            return True
        except Exception as e:
            print(f"[Discovery] Failed to register mDNS: {e}")
            return False

    def stop(self):
        if self.zeroconf and self.info:
            try:
                self.zeroconf.unregister_service(self.info)
                self.zeroconf.close()
            except Exception:
                pass
