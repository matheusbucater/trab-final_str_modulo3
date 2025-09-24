import socket
import json
import random
import time
from datetime import datetime, timezone

# Configurações de rede
BROADCAST_IP = "127.255.255.255"
PORT = 3333

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

# Função para gerar evento CEP
def gerar_evento_cep(idCidade, numPct):
    # número de consumidores afetados (pode chegar a milhares)
    eventos_associados = random.randint(1000, 30000)
    
    # descrição baseada na quantidade
    if eventos_associados < 5000:
        descricao = "Queda localizada em alguns bairros"
    elif eventos_associados < 15000:
        descricao = "Interrupção de energia em vários setores"
    else:
        descricao = "Grande falha regional - possível problema em subestação principal"
    
    return {
        "URI": "CEP/Alarm",
        "idCidade": idCidade,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nroEventosAssociados": eventos_associados,
        "descricao": descricao
    }

# Simulação
cidades = ["Uberlandia", "Araguari", "Patos de Minas", "Ituiutaba"]
numPct = 0

try:
    while True:
        numPct += 1
        cidade = random.choice(cidades)

        pacote = gerar_evento_cep(cidade, numPct)
        mensagem = json.dumps(pacote).encode("utf-8")

        sock.sendto(mensagem, (BROADCAST_IP, PORT))
        print(f"Enviado CEP/Alarm: {pacote['descricao']} ({pacote['nroEventosAssociados']} eventos) - numPct={numPct}")

        # CEP gera alarmes mais esporádicos (a cada 5–15 segundos)
        time.sleep(random.uniform(5, 15))

except KeyboardInterrupt:
    print("\nSimulação encerrada.")
    sock.close()

