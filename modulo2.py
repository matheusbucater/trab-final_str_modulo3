import socket
import string
import json
import random
import time
from datetime import datetime, timezone

IP = "127.255.255.255"
PORT = 3333

def gerar_evento_inicio(idIED, funcao, numPct):
    tensao = round(random.uniform(218, 222), 2)
    corrente = round(random.uniform(9, 12), 2)
    freq = round(random.uniform(59.8, 60.2), 2)

    if funcao == "50":
        corrente = round(random.uniform(40, 80), 2)
    elif funcao == "51":
        corrente = round(random.uniform(20, 35), 2)

    potApaVA = round(tensao * corrente, 2)
    fatorP = round(random.uniform(0.7, 0.95), 3)
    potRealW = round(potApaVA * fatorP, 2)
    potReatVAr = round((potApaVA**2 - potRealW**2) ** 0.5, 2)
    angTensao = round(random.uniform(-20, 20), 2)

    return {
        "URI": "200/1",
        "idIED": idIED,
        "funcaoProtecao": funcao,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "medidas": {
            "fase": random.choice(["A", "B", "C"]),
            "tensao": tensao,
            "corrente": corrente,
            "angTensao": angTensao,
            "potApaVA": potApaVA,
            "potReatVAr": potReatVAr,
            "potRealW": potRealW,
            "fatorP": fatorP,
            "freq": freq
        }
    }

def gerar_evento_fim(idIED, funcao, numPct):
    return {
        "URI": "200/2",
        "idIED": idIED,
        "funcaoProtecao": funcao,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    
    numPct = 0
    try:
        while True:
            idIED = f"IED_{random.choice(string.ascii_uppercase)}{random.randint(0,11)}"
            numPct += 1
    
            if random.random() < 0.9:
                print("Nenhum evento detectado...")
                time.sleep(1)
                continue
    
            funcao = random.choice(["50", "51"])
            evento_inicio = gerar_evento_inicio(idIED, funcao, numPct)
            mensagem = json.dumps(evento_inicio).encode("utf-8")
            sock.sendto(mensagem, (IP, PORT))
            print(f"Enviado INICIO de proteção {funcao} - numPct={numPct}")
    
            duracao = random.uniform(2, 6)
            time.sleep(duracao)
    
            numPct += 1
            evento_fim = gerar_evento_fim(idIED, funcao, numPct)
            mensagem = json.dumps(evento_fim).encode("utf-8")
            sock.sendto(mensagem, (IP, PORT))
            print(f"Enviado FIM de proteção {funcao} - numPct={numPct}")
    
            time.sleep(2)
    
    except KeyboardInterrupt:
        print("\nSimulação encerrada.")
        sock.close()

if __name__ == "__main__":
    main()
