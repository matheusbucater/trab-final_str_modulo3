import string
import socket
import json
import random
import time
from datetime import datetime, timezone

IP = "127.255.255.255"
PORT = 3333

def gerar_medida(fase, freq=60.0):
    tensao = round(random.uniform(218, 222), 2)
    corrente = round(random.uniform(9, 12), 2)
    potRealW = round(tensao * corrente * random.uniform(0.8, 0.95), 2)  # ~fator de potência
    potApaVA = round(tensao * corrente, 2)
    potReatVAr = round((potApaVA**2 - potRealW**2) ** 0.5, 2)  # triângulo de potências
    fatorP = round(potRealW / potApaVA, 3)
    angTensao = round(random.uniform(-10, 10), 2)  # em graus

    return {
        "fase": fase,
        "tensao": tensao,
        "corrente": corrente,
        "angTensao": angTensao,
        "potApaVA": potApaVA,
        "potReatVAr": potReatVAr,
        "potRealW": potRealW,
        "fatorP": fatorP,
        "freq": freq
    }

def gerar_pacote_99_1(idMU, idAtivo, numPct):
    return {
        "URI": "99/1",
        "idMU": idMU,
        "idAtivo": idAtivo,
        "numPct": numPct,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "freqEnvioMS": 50,
        "medidas": [
            gerar_medida("A"),
            gerar_medida("B"),
            gerar_medida("C")
        ]
    }

# Função para gerar pacote 99/2 (urgente, com discrepância)
def gerar_pacote_99_2(idMU, idAtivo, numPct):
    medidas = [
        gerar_medida("A"),
        gerar_medida("B"),
        gerar_medida("C")
    ]

    medidas[0]["corrente"] = round(random.uniform(30, 40), 2)
    medidas[0]["potApaVA"] = round(medidas[0]["tensao"] * medidas[0]["corrente"], 2)
    medidas[0]["potRealW"] = round(medidas[0]["potApaVA"] * random.uniform(0.7, 0.9), 2)
    medidas[0]["potReatVAr"] = round((medidas[0]["potApaVA"]**2 - medidas[0]["potRealW"]**2) ** 0.5, 2)
    medidas[0]["fatorP"] = round(medidas[0]["potRealW"] / medidas[0]["potApaVA"], 3)

    return {
        "URI": "99/2",
        "idMU": idMU,
        "idAtivo": idAtivo,
        "numPct": numPct,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "medidas": medidas,
        "variavelDiscrepante": "corrente",
        "faseDiscrepante": "A"
    }

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    
    numPct = 0
    try:
        while True:
            idMU = random.randint(0,11)
            idAtivo = f"IED_{random.choice(string.ascii_uppercase)}{random.randint(0, 11)}"
            numPct += 1
    
            if random.random() < 0.9:
                pacote = gerar_pacote_99_1(idMU, idAtivo, numPct)
            else:
                pacote = gerar_pacote_99_2(idMU, idAtivo, numPct)
    
            mensagem = json.dumps(pacote).encode("utf-8")
            sock.sendto(mensagem, (IP, PORT))
    
            print(f"Enviado: {pacote['URI']} - numPct={numPct}")
    
            time.sleep(0.05)
    
    except KeyboardInterrupt:
        print("\nSimulação encerrada.")
        sock.close()

if __name__ == "__main__":
    main()
