import asyncio
import argparse
import struct
import json
from functools import partial


logger = None


class TcpTunnel(object):
    HEADER_SIZE = 4
    
    def __init__(self) -> None:
        self.port_mapping = dict()
        self.servers = []

    def add_port_mapping(self, local_port, server_host, server_port, remote_host, remote_port):
        self.port_mapping[local_port] = (server_host, server_port, remote_host, remote_port)

    def add_server(self, server_port, server_host='0.0.0.0'):
        self.servers.append((server_host, server_port))

    def start(self):
        async def _start_acceptors():
            acceptors = []
            for server in self.servers:
                acceptors.append(asyncio.create_task(self._create_server(server[0], server[1], self.server_handle)))
            for local_port, tunnel_info in self.port_mapping.items():
                acceptors.append(asyncio.create_task(self._create_server('0.0.0.0', local_port, partial(self.local_handle, tunnel_info))))
            tasks = asyncio.gather(*acceptors, return_exceptions=True)
            await tasks
        TcpTunnel._run(_start_acceptors())

    async def server_handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        data = await reader.read(self.HEADER_SIZE)
        if len(data) != self.HEADER_SIZE:
            writer.close()
            return
        size = struct.unpack('!I', data[:self.HEADER_SIZE])[0]
        data = await reader.read(size)
        while len(data) < size and not reader.at_eof():
            data += await reader.read(size - len(data))
        tunnel_req = json.loads(data.decode())
        dst_reader, dst_writer = await asyncio.open_connection(tunnel_req['dst_host'], tunnel_req['dst_port'])
        conn_msg = f"{reader._transport._extra['peername']} <==> {dst_reader._transport._extra['sockname']} <==> {dst_reader._transport._extra['peername']}'"
        logger.info(f"[server] [connect]    {conn_msg}")
        await asyncio.wait([self.trans(dst_reader, writer), self.trans(reader, dst_writer)])
        logger.info(f"[server] [disconnect] {conn_msg}")

    async def local_handle(self, tunnel_info, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        server_host, server_port, remote_host, remote_port = tunnel_info
        remote_reader, remote_writer = await asyncio.open_connection(server_host, server_port)
        tunnel_req = json.dumps({'dst_host': remote_host, 'dst_port': remote_port}).encode()
        remote_writer.write(struct.pack('!I', len(tunnel_req)))
        remote_writer.write(tunnel_req)
        conn_msg = f"{reader._transport._extra['peername']} <==> ('{server_host}', {server_port}) <==> ('{remote_host}', {remote_port})"
        logger.info(f"[client] [connect]    {conn_msg}")
        await asyncio.wait([self.trans(reader, remote_writer), self.trans(remote_reader, writer)])
        logger.info(f"[client] [disconnect] {conn_msg}")
        

    async def trans(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        while not reader.at_eof() and not writer.is_closing():
            data = await reader.read(4096)
            writer.write(data)
        if not reader.at_eof():
            reader.feed_eof()
        if not writer.is_closing():
            writer.close()

    @staticmethod
    async def _create_server(host, port, handle):
        server = await asyncio.start_server(handle, host, port)
        async with server:
            await server.serve_forever()

    @staticmethod
    def _run(coroutine):
        try:
            asyncio.run(coroutine)
        except KeyboardInterrupt:
            pass
        finally:
            pass


def parse_server_addr(s):
    fields = s.split(':')
    if len(fields) == 1:
        return '0.0.0.0', int(fields[0])
    else:
        return fields[0], int(fields[1])

def parse_remote(s):
    host, port = s.split(':')
    return host, int(port)

def parse_args():
    parser = argparse.ArgumentParser(description='tcp tunnel')
    parser.add_argument('-t', '--tunnel', action='append', required=False)
    parser.add_argument('-s', '--server', type=parse_server_addr, default=None, required=False)
    parser.add_argument('-r', '--remote', type=parse_remote, default=(None, None), required=False)
    args = parser.parse_args()
    
    if args.tunnel is not None:
        def parse_tunnel_conf(conf, server_host, server_port):
            fields = conf.split(':')
            if len(fields) == 3:
                return int(fields[0]), server_host, server_port, fields[1], int(fields[2])
            return int(fields[0]), fields[1], int(fields[2]), fields[3], int(fields[4])

        for i in range(len(args.tunnel)):
            args.tunnel[i] = parse_tunnel_conf(args.tunnel[i], args.remote[0], args.remote[1])
    
    return args     


def get_logger():
    import logging
    import logging.handlers
    logger = logging.getLogger("tcp_tunnel_logger")
    logger.setLevel(logging.INFO)
    channel = logging.handlers.RotatingFileHandler(filename="tcp_tunnel.log", maxBytes=100*1024*1024, backupCount=2)
    formatter = logging.Formatter("%(asctime)s|%(filename)s:%(lineno)s|%(levelname)s|%(message)s")
    channel.setFormatter(formatter)
    logger.addHandler(channel)
    return logger


def main():
    global logger
    logger = get_logger()

    tunnel = TcpTunnel()
    args = parse_args()
    if args.server is not None:
        tunnel.add_server(server_port=args.server[1], server_host=args.server[0])
    if args.tunnel is not None:
        for tun in args.tunnel:
            tunnel.add_port_mapping(*tun)

    tunnel.start()


if __name__ == '__main__':
    main()
