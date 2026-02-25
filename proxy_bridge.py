"""
Local HTTP proxy bridge: listens on 0.0.0.0:8888 (no auth) and forwards
all traffic to an upstream authenticated HTTP proxy.

This solves Chrome's repeated proxy auth dialog issue on Android.
AVD connects to host_ip:8888 (no auth needed), traffic flows through
authenticated upstream proxy.
"""
import sys
import socket
import threading
import base64
import select

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 8888


def forward_data(src, dst, timeout=60):
    """Forward data between two sockets."""
    try:
        while True:
            ready = select.select([src], [], [], timeout)
            if ready[0]:
                data = src.recv(32768)
                if not data:
                    break
                dst.sendall(data)
            else:
                break
    except:
        pass
    finally:
        try: src.close()
        except: pass
        try: dst.close()
        except: pass


def handle_connect(client_sock, upstream_host, upstream_port, upstream_user, upstream_pass):
    """Handle CONNECT tunnel through upstream proxy."""
    try:
        # Read the CONNECT request from client
        request = b""
        while b"\r\n\r\n" not in request:
            data = client_sock.recv(4096)
            if not data:
                return
            request += data
        
        # Extract target from CONNECT
        first_line = request.split(b"\r\n")[0].decode()
        # CONNECT host:port HTTP/1.1
        target = first_line.split()[1]
        
        # Connect to upstream proxy
        upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        upstream.settimeout(30)
        upstream.connect((upstream_host, upstream_port))
        
        # Send CONNECT to upstream with auth
        auth = base64.b64encode(f"{upstream_user}:{upstream_pass}".encode()).decode()
        upstream_request = (
            f"CONNECT {target} HTTP/1.1\r\n"
            f"Host: {target}\r\n"
            f"Proxy-Authorization: Basic {auth}\r\n"
            f"\r\n"
        ).encode()
        upstream.sendall(upstream_request)
        
        # Read upstream response
        response = b""
        while b"\r\n\r\n" not in response:
            data = upstream.recv(4096)
            if not data:
                client_sock.close()
                upstream.close()
                return
            response += data
        
        # Check if upstream accepted
        status_line = response.split(b"\r\n")[0].decode()
        if "200" in status_line:
            # Tell client connection established
            client_sock.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            
            # Bidirectional forwarding
            t1 = threading.Thread(target=forward_data, args=(client_sock, upstream), daemon=True)
            t2 = threading.Thread(target=forward_data, args=(upstream, client_sock), daemon=True)
            t1.start()
            t2.start()
            t1.join()
            t2.join()
        else:
            client_sock.sendall(f"HTTP/1.1 502 Bad Gateway\r\n\r\n{status_line}".encode())
            client_sock.close()
            upstream.close()
    except Exception as e:
        try: client_sock.close()
        except: pass


def handle_http(client_sock, request, upstream_host, upstream_port, upstream_user, upstream_pass):
    """Handle regular HTTP request through upstream proxy."""
    try:
        # Connect to upstream
        upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        upstream.settimeout(30)
        upstream.connect((upstream_host, upstream_port))
        
        # Add proxy auth header
        auth = base64.b64encode(f"{upstream_user}:{upstream_pass}".encode()).decode()
        
        # Insert Proxy-Authorization header
        lines = request.split(b"\r\n")
        new_lines = [lines[0]]
        new_lines.append(f"Proxy-Authorization: Basic {auth}".encode())
        new_lines.extend(lines[1:])
        modified_request = b"\r\n".join(new_lines)
        
        upstream.sendall(modified_request)
        
        # Forward response back
        while True:
            ready = select.select([upstream], [], [], 30)
            if ready[0]:
                data = upstream.recv(32768)
                if not data:
                    break
                client_sock.sendall(data)
            else:
                break
        
        upstream.close()
        client_sock.close()
    except:
        try: client_sock.close()
        except: pass
        try: upstream.close()
        except: pass


def handle_client(client_sock, upstream_host, upstream_port, upstream_user, upstream_pass):
    """Handle incoming client connection."""
    try:
        request = b""
        while b"\r\n\r\n" not in request:
            data = client_sock.recv(4096)
            if not data:
                client_sock.close()
                return
            request += data
        
        first_line = request.split(b"\r\n")[0].decode()
        method = first_line.split()[0].upper()
        
        if method == "CONNECT":
            handle_connect(client_sock, upstream_host, upstream_port, upstream_user, upstream_pass)
        else:
            handle_http(client_sock, request, upstream_host, upstream_port, upstream_user, upstream_pass)
    except Exception as e:
        try: client_sock.close()
        except: pass


def run_proxy_bridge(upstream_host, upstream_port, upstream_user, upstream_pass):
    """Run local proxy bridge."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((LISTEN_HOST, LISTEN_PORT))
    server.listen(50)
    
    print(f"Proxy bridge listening on {LISTEN_HOST}:{LISTEN_PORT}")
    print(f"Forwarding to {upstream_host}:{upstream_port} (auth={upstream_user[:5]}...)")
    
    while True:
        client_sock, addr = server.accept()
        t = threading.Thread(
            target=handle_client,
            args=(client_sock, upstream_host, upstream_port, upstream_user, upstream_pass),
            daemon=True
        )
        t.start()


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: python proxy_bridge.py <upstream_host> <upstream_port> <user> <pass>")
        sys.exit(1)
    
    run_proxy_bridge(sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4])
