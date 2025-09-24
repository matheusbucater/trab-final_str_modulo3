import string
import socket
import json
import random
import time
from datetime import datetime, timezone

IP = "127.255.255.255"
PORT = 3333


def gerar_evento_acumulado(idIED, numPct):
    return {
        "URI": "400/1",
        "idIED": idIED,
        "tipoEvento": random.choice(["SobrecorrenteAcumulada", "SubtensaoAcumulada", "OscilacaoFrequencia"]),
        "nroEventosAcumulados": random.randint(1, 50),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    
    numPct = 0
    try:
        while True:
            numPct += 1
            idIED = f"IED_{random.choice(string.ascii_uppercase)}{random.randint(0,11)}"
    
            pacote = gerar_evento_acumulado(idIED, numPct)
            mensagem = json.dumps(pacote).encode("utf-8")
    
            sock.sendto(mensagem, (IP, PORT))
            print(f"Enviado evento acumulado {pacote['tipoEvento']} de {idIED} - numPct={numPct}")
    
            time.sleep(random.uniform(2, 6))
    
    except KeyboardInterrupt:
        print("\nSimulação encerrada.")
        sock.close()

if __name__ == "__main__":
    main()
