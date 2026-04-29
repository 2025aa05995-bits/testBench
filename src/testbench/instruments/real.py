import socket
from typing import Any, Dict, List, Optional

from .base import InstrumentBase
from ..config_manager import ConfigManager


class RealInstrumentAdapter(InstrumentBase):
    """A generic real instrument adapter supporting VISA, TCP/IP, and Serial."""

    ACTIONS = {
        'connect': 'Connect to instrument via configured transport',
        'disconnect': 'Disconnect from the instrument',
        'identify': 'Query instrument identity string',
        'status': 'Get instrument connection status',
        'raw': 'Send raw SCPI command or query',
        'reset': 'Send *RST to the instrument',
    }

    def __init__(self, category: str, config_manager: ConfigManager):
        super().__init__(resource_name=None)
        self.category = category
        self.config_manager = config_manager
        self.protocol = self.config_manager.get_protocol(category)
        self._timeout = self.config_manager.get_timeout(category) / 1000.0
        self._connection = None
        self.connected = False
        self.resource_name = self._compute_resource_name()

    def _compute_resource_name(self) -> str:
        if self.protocol.lower() == 'serial':
            port = self.config_manager.get_serial_port(self.category)
            return port or f"SERIAL:{self.category}"

        if self.protocol.lower() in {'tcp/ip', 'tcp', 'ip'}:
            ip = self.config_manager.get_ip_address(self.category) or 'unknown'
            port = self.config_manager.get_port(self.category)
            return f"{ip}:{port}"

        return self.config_manager.get_visa_resource(self.category) or self.category

    def connect(self, address: Optional[str] = None) -> None:
        if self.connected:
            return

        if address:
            self.resource_name = address

        if self.protocol.lower() in {'visa', 'usb'}:
            self._connection = self._open_visa_connection(self.resource_name)
        elif self.protocol.lower() in {'tcp/ip', 'tcp', 'ip'}:
            ip = self.config_manager.get_ip_address(self.category)
            port = self.config_manager.get_port(self.category)
            if not ip:
                raise ValueError(f"No IP address configured for {self.category}")
            self._connection = self._open_socket_connection(ip, port)
            self.resource_name = f"{ip}:{port}"
        elif self.protocol.lower() == 'serial':
            port = self.config_manager.get_serial_port(self.category)
            baudrate = self.config_manager.get_baudrate(self.category)
            if not port:
                raise ValueError(f"No serial port configured for {self.category}")
            self._connection = self._open_serial_connection(port, baudrate)
            self.resource_name = port
        else:
            raise ValueError(f"Unsupported protocol: {self.protocol}")

        self.connected = True

    def disconnect(self) -> None:
        if self._connection is None:
            self.connected = False
            return

        try:
            if hasattr(self._connection, 'close'):
                self._connection.close()
        except Exception:
            pass
        finally:
            self._connection = None
            self.connected = False

    def reset(self) -> None:
        self.raw('*RST')

    def identify(self) -> str:
        return self.raw('*IDN?')

    def status(self) -> Dict[str, Any]:
        return {
            'category': self.category,
            'protocol': self.protocol,
            'resource': self.resource_name,
            'connected': self.connected,
        }

    def configure(self, **settings: Any) -> None:
        if self.connected and 'timeout_ms' in settings:
            self._timeout = settings['timeout_ms'] / 1000.0

    def measure(self, parameter: str) -> Any:
        return self.raw(parameter)

    def raw(self, command: str) -> Any:
        if not self.connected:
            raise RuntimeError('Not connected')

        command = command.strip()
        if not command:
            raise ValueError('Raw command cannot be empty')

        if command.endswith('?'):
            return self._query(command)

        self._write(command)
        return 'OK'

    def execute(self, action: str, args: List[str]) -> Any:
        if action == 'connect':
            return self.connect(' '.join(args) if args else None)
        if action == 'disconnect':
            return self.disconnect()
        if action == 'identify':
            return self.identify()
        if action == 'status':
            return self.status()
        if action == 'reset':
            return self.reset()
        if action == 'raw':
            return self.raw(' '.join(args))
        raise ValueError(f'Unknown real instrument action: {action}')

    def _open_visa_connection(self, resource: str):
        try:
            import pyvisa
        except ImportError as exc:
            raise ImportError('pyvisa is required for VISA/USB connections') from exc

        rm = pyvisa.ResourceManager()
        visa = rm.open_resource(resource)
        visa.timeout = int(self._timeout * 1000)
        return visa

    def _open_socket_connection(self, ip: str, port: int):
        sock = socket.create_connection((ip, port), timeout=self._timeout)
        sock.settimeout(self._timeout)
        return sock

    def _open_serial_connection(self, port: str, baudrate: int):
        try:
            import serial
        except ImportError as exc:
            raise ImportError('pyserial is required for Serial connections') from exc

        ser = serial.Serial(port=port, baudrate=baudrate, timeout=self._timeout)
        return ser

    def _write(self, command: str) -> None:
        if hasattr(self._connection, 'write'):
            if self.protocol.lower() == 'serial':
                self._connection.write(command.encode('utf-8') + b'\n')
            else:
                self._connection.write(command)
            return
        if hasattr(self._connection, 'sendall'):
            self._connection.sendall(command.encode('utf-8') + b'\n')
            return
        raise RuntimeError('Unsupported connection type for writing')

    def _read(self) -> str:
        if hasattr(self._connection, 'read'):
            result = self._connection.read().decode('utf-8', errors='ignore')
            return result.strip()
        if hasattr(self._connection, 'recv'):
            data = b''
            while True:
                chunk = self._connection.recv(4096)
                if not chunk:
                    break
                data += chunk
                if data.endswith(b'\n') or data.endswith(b'\r'):
                    break
            return data.decode('utf-8', errors='ignore').strip()
        raise RuntimeError('Unsupported connection type for reading')

    def _query(self, command: str) -> Any:
        if hasattr(self._connection, 'query'):
            return self._connection.query(command)
        self._write(command)
        return self._read()
