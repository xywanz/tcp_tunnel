# tcp_tunnel

## usage

```bash
# server
python3 tcp_tunnel.py --server=[bind_host:]port
```

```bash
# client
python3 tcp_tunnel.py --remote=<remote_host>:<remote_port> [-t <local_port>:<dst_addr>:<dst_port> ...]
```

## requirements

Python>=3.7
