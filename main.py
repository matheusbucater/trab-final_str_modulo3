#!/usr/bin/env python3
"""
Módulo 3 - Monitoramento. Versão com GUI Tkinter integrada.

- Thread 0 (main): cria socket, filas, eventos, inicia threads de recepção, processamento e armazenamento
- GUI (executada no main thread) consome queue_gui e mostra séries históricas + alarmes
"""

# ----------------------------
# Importações
# ----------------------------
import socket
import threading
import queue
import itertools
import time
import json
import logging
from datetime import datetime, timezone
from collections import defaultdict, deque
import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib
matplotlib.use("TkAgg")
from dataclasses import dataclass
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates

# ----------------------------
# Constantes
# ----------------------------
BIND_ADDRESS = ""
PORT = 3333
RECV_BUFFER = 65536
SOCKET_TIMEOUT = 1.0
LOG_LEVEL = logging.INFO
GUI_REFRESH_MS = 500

# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("modulo3_gui")

# ----------------------------
# Mapeamento de prioridade 
# (n menor => maior prioridade)
# ----------------------------
PRIORITY_MAP = {
    "200/1": 1,
    "200/2": 1,
    "99/2": 2,
    "400/1": 3,
    "CEP/Alarm": 4,
    "99/1": 5,
}

# ----------------------------
# Mapeamento do formato dos
# pacotes para tipos/classes
# ----------------------------
@dataclass
class MedidasEletricas():
    fase: str
    tensao: float
    corrente: float
    potRealW: float
    angTensao: float
    potApaVA: float
    potReatVAr: float
    potRealW: float
    fatorP: float
    freq: float

@dataclass
class Pkt991():
    idMU: int
    idAtivo: str | None
    numPct: int
    timestamp: datetime
    freqEnvioMS: int
    medidas: [MedidasEletricas]
    URI: str = "99/1"

@dataclass
class Pkt992():
    idMU: int
    idAtivo: str | None
    numPct: int
    timestamp: datetime
    medidas: [MedidasEletricas]
    variavelDiscrepante: str
    faseDiscrepante: str
    URI: str = "99/2"

@dataclass 
class PktCEPAlarm():
    idCidade: str
    timestamp: datetime
    nroEventosAssociados: int
    descricao: str
    URI: str = "CEP/Alarm"

@dataclass 
class Pkt2001():
    idIED: str
    timestamp: datetime
    funcaoProtecao: str
    medidas: [MedidasEletricas]
    URI: str = "200/1"

@dataclass 
class Pkt2002():
    idIED: str
    timestamp: datetime
    funcaoProtecao: str
    URI: str = "200/2"

@dataclass 
class Pkt4001():
    idIED: str
    timestamp: datetime
    tipoEvento: str
    nroEventosAcumulados: int
    URI: str = "400/1"

# ----------------------------
# Implementação das Threads
# ----------------------------
def thread_recepcao(recv_sock, priority_queue, shutdown_event, seq_counter):
    """
    Thread 1 - Recepção de pacotes
    Recebe os pacotes UDP, decodifica JSON e insere na priority_queue.
    """
    log.info("[RECV] iniciada.")
    recv_sock.settimeout(SOCKET_TIMEOUT)
    while not shutdown_event.is_set():
        try:
            data, addr = recv_sock.recvfrom(RECV_BUFFER)
        except socket.timeout:
            continue
        except Exception as e:
            log.exception("[RECV] Erro no socket")
            time.sleep(0.5)
            continue

        try:
            raw = data.decode("utf-8", errors="replace")
            log.debug("[RECV] pacote recebido de %s: %s", addr, raw)
            pkt = json.loads(raw)
        except Exception as e:
            log.warning("[RECV] JSON inválido de %s: %s. Ignorando pacote...", addr, e)
            continue

        uri = pkt.get("URI", "")
        priority = PRIORITY_MAP.get(uri, PRIORITY_MAP["99/1"])
        seq = pkt.get("numPct", next(seq_counter))
        priority_queue.put((priority, seq, pkt))
        log.debug("[RECV] novo pacote inserido na fila (URI=%s PRIO=%s SEQ=%s).", uri, priority, seq)

    log.info("[RECV] finalizando.")


def thread_processamento(priority_queue, queue_gui, queue_db, shutdown_event):
    """
    Thread 2 - Processamento
    Consome os pacotes priority_queue, interpreta os dados e insere nas filas queue_gui e queue_db.
    """
    log.info("[PROC] iniciada.")
    while not shutdown_event.is_set():
        try:
            priority, seq, pkt = priority_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        uri = pkt.get("URI", "UNKNOWN")

        dados = None

        match uri:
            case "99/1":
                dados = Pkt991(**pkt)
            case "99/2":
                dados = Pkt992(**pkt)
            case "200/1":
                dados = Pkt2001(**pkt)
            case "200/2":
                dados = Pkt2002(**pkt)
            case "400/1":
                dados = Pkt4001(**pkt)
            case "CEP/Alarm":
                dados = PktCEPAlarm(**pkt)
            case _:
                log.warning("[PROC] URI inválido. Ignorando pacote...")
                continue

        try:
            queue_gui.put_nowait(dados)
            queue_db.put_nowait(dados)
        except queue.Full:
            log.warning("[PROC] Fila cheia.")

        priority_queue.task_done()

    log.info("[PROC] finalizando")


def thread_armazenamento(queue_db, shutdown_event):
    """
    TODO
    Thread 3 - Armazenamento
    Consome os pacotes de queue_db e persiste no banco de dados.
    """
    log.info("[DB] iniciada.")
    while not shutdown_event.is_set():
        try:
            item = queue_db.get(timeout=0.5)
        except queue.Empty:
            continue

        queue_db.task_done()

    log.info("[DB] finalizando.")

def nested_dict():
    """
    Função auxiliar para criar um dicionário aninhado
    """
    return defaultdict(nested_dict)

# ----------------------------
# Interface Gráfica
# ----------------------------
class Modulo3GUI:
    def __init__(self, root, queue_gui, shutdown_event):
        self.root = root
        self.queue_gui = queue_gui
        self.shutdown_event = shutdown_event

        self.root.title("STR_MODULO3_V1 - Monitoramento")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Dados em memória
        self.series = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        self.alarms = []

        # IEDs e parâmetros para filtros
        self.mu_set = set()
        self.medida_set = set([
            "tensao", "corrente", "potRealW",
            "angTensao", "potApaVA", "potReatVAr", 
            "potRealW", "fatorP", "freq"
        ])
        self.fase_set = set(["A", "B", "C"])
        self.alarm_set = set(["todos", "200/X", "400/1", "CEP/Alarm"])

        # Containers principais
        self.left_frame = ttk.Frame(root, padding=8)
        self.center_frame = ttk.Frame(root, padding=8)
        self.right_frame = ttk.Frame(root, padding=8)

        self.left_frame.grid(row=0, column=0, sticky="ns")
        self.center_frame.grid(row=0, column=1, sticky="nsew")
        self.right_frame.grid(row=0, column=2, sticky="ns")

        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        self._build_left_panel()

        self._build_center_panel()

        self._build_right_panel()

        self.root.after(GUI_REFRESH_MS, self._periodic_poll)

    def _build_left_panel(self):
        """
        Inicializa a interface dos filtros de gráfico.
        """
        ttk.Label(self.left_frame, text="Merge Unit").pack(anchor="w")
        self.device_var = tk.StringVar()
        self.device_var.trace_add("write", lambda *args: self._redraw_plot())
        self.device_menu = ttk.Combobox(self.left_frame, textvariable=self.device_var, values=list(self.mu_set), state="readonly")
        self.device_menu.pack(fill="x", pady=4)

        ttk.Label(self.left_frame, text="Fase").pack(anchor="w", pady=(8,0))
        self.fase_var = tk.StringVar(value="A")
        self.fase_var.trace_add("write", lambda *args: self._redraw_plot())
        self.fase_menu = ttk.Combobox(self.left_frame, textvariable=self.fase_var, values=list(self.fase_set), state="readonly")
        self.fase_menu.pack(fill="x", pady=4)

        ttk.Label(self.left_frame, text="Medida").pack(anchor="w", pady=(16,0))
        self.medida_var = tk.StringVar(value="tensao")
        self.medida_var.trace_add("write", lambda *args: self._redraw_plot())
        self.medida_menu = ttk.Combobox(self.left_frame, textvariable=self.medida_var, values=list(self.medida_set), state="readonly")
        self.medida_menu.pack(fill="x", pady=4)

    def _build_center_panel(self):
        """
        Inicializa a interface do gráfico.
        """
        ttk.Label(self.center_frame, text="STR_MODULO3_V1", font=("Helvetica", 12, "bold")).pack()
        self.fig = Figure(figsize=(6,3), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_xlabel("tempo")
        self.ax.set_ylabel("tensao")
        self.ax.set_title("Série histórica das medidas elétricas")
        self.ax.grid(True)
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))  # or "%Y-%m-%d %H:%M"
        self.ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        self.fig.autofmt_xdate()
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.center_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill="both", expand=True)

    def _build_right_panel(self):
        """
        Inicializa a interface dos alarmes/filtro de alarme.
        """
        ttk.Label(self.right_frame, text="Alarmes/Eventos ativos", font=("Helvetica", 12, "bold")).pack()

        ttk.Label(self.right_frame, text="Filtro").pack(anchor="w", pady=(0,2))
        self.alarm_var = tk.StringVar(value="todos")
        self.alarm_var.trace_add("write", lambda *args: self._redraw_alarms())
        self.alarm_menu = ttk.Combobox(self.right_frame, textvariable=self.alarm_var, values=list(self.alarm_set), state="readonly")
        self.alarm_menu.pack(fill="x", pady=(0,10))

        self.alarm_container = ttk.Frame(self.right_frame)
        self.alarm_container.pack(fill="both", expand=True, pady=6)

    def _periodic_poll(self):
        """
        Consome a queue_gui e atualiza as estruturas utilizadas para desenhar a interface (self.alarms e self.series)
        """
        updated_series = False
        updated_alarms = False
        while True:
            try:
                item = self.queue_gui.get_nowait()
            except queue.Empty:
                break

            match item:
                case Pkt991() | Pkt992():
                    id_ = f"MU_{item.idMU}"
                    medidas = item.medidas
                    ts = item.timestamp
                    self.add_medidas(id_, ts, medidas)
                    self.mu_set.add(id_)
                    self.device_menu["values"] = list(self.mu_set)
                    updated_series = True
                case Pkt2001() | Pkt2002():
                    alarme_evento = {
                        "uri": item.URI,
                        "id": f"{item.idIED}_{item.funcaoProtecao}",
                        "title": f"[{item.URI}] {item.idIED}",
                        "descricao": (
                            f"[{datetime.fromisoformat(item.timestamp).strftime("%Y-%m-%d %H:%M:%S")}]\nFunção {item.funcaoProtecao} iniciada.\nMedidas:\n{item.medidas}" 
                            if hasattr(item, "medidas") else
                            f"[{datetime.fromisoformat(item.timestamp).strftime("%Y-%m-%d %H:%M:%S")}]\nFunção {item.funcaoProtecao} encerrada"
                        )
                    }
                    self.alarms.append(alarme_evento)
                    updated_alarms = True
                case Pkt4001():
                    alarme_evento = {
                        "uri": item.URI,
                        "id": f"{item.idIED}_{item.tipoEvento}",
                        "title": f"[{item.URI}] {item.idIED}",
                        "descricao": f"[{datetime.fromisoformat(item.timestamp).strftime("%Y-%m-%d %H:%M:%S")}]\nEvento {item.tipoEvento} ocorreu {item.nroEventosAcumulados}x no {item.idIED}"
                    }
                    self.alarms.append(alarme_evento)
                    updated_alarms = True
                case PktCEPAlarm():
                    alarme_evento = {
                        "uri": item.URI,
                        "id": f"{item.idCidade}",
                        "title": f"[{item.URI}] {item.idCidade}",
                        "descricao": f"[{datetime.fromisoformat(item.timestamp).strftime("%Y-%m-%d %H:%M:%S")}]\nEvento \"{item.descricao}\" ocorreu {item.nroEventosAssociados}x em {item.idCidade}",
                    }
                    self.alarms.append(alarme_evento)
                    updated_alarms = True
                case _:
                    log.warning("[PROC] URI inválido. Ignorando pacote...")
                    continue

            self.queue_gui.task_done()

        if updated_series:
            self._redraw_plot()
        if updated_alarms:
            self._redraw_alarms()

        # schedule next poll
        if not self.shutdown_event.is_set():
            self.root.after(GUI_REFRESH_MS, self._periodic_poll)

    def _redraw_plot(self):
        """
        Desenha o gráfico
        """
        self.ax.clear()
        self.ax.set_title("Série histórica das medidas elétricas")
        self.ax.set_xlabel("tempo")
        self.ax.set_ylabel(self.medida_var.get())
        self.ax.grid(True)

        # quais dispositivos desenhar?
        devfilter = self.device_var.get()
        medidafilter = self.medida_var.get()
        fasefilter = self.fase_var.get()

        if devfilter != "" and devfilter is not None:
            data = self.series.get(devfilter).get(medidafilter).get(fasefilter)
            xs = [datetime.fromisoformat(x[0]) for x in data] 
            ys = [x[1] for x in data]

            self.ax.plot(xs, ys, label=devfilter, color="blue", marker="o")
        
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))  # or "%Y-%m-%d %H:%M"
        self.ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        self.fig.autofmt_xdate()

        self.canvas.draw_idle()

    def _redraw_alarms(self):
        """
        Desenha os alarmes
        """
        for child in self.alarm_container.winfo_children():
            child.destroy()

        alarmes = []
        alarmfilter = self.alarm_var.get()
        match alarmfilter:
            case "200/X":
                alarmes = [alarme for alarme in self.alarms if alarme["uri"] == "200/1" or alarme["uri"] == "200/2"]
            case "400/1":
                alarmes = [alarme for alarme in self.alarms if alarme["uri"] == "400/1"]
            case "CEP/Alarm":
                alarmes = [alarme for alarme in self.alarms if alarme["uri"] == "CEP/Alarm"]
            case _:
                alarmes = self.alarms

        
        for alarm in alarmes[-20:]:
            uri = alarm["uri"]
            alarm_id = alarm["id"]
            alarm_title = alarm["title"]
            alarm_desc = alarm["descricao"]
            bg = "#FF66FF"
            if uri == "CEP/Alarm":
                bg = "#FFFF33"
            elif uri == "200/1":
                bg = "#FF0000"
            elif uri == "200/2":
                bg = "#33FF33"
            elif uri == "400/1":
                bg = "#FF9933"

            frame = tk.Frame(self.alarm_container, bg=bg, bd=1, relief="solid")
            frame.pack(fill="x", pady=3, padx=2)

            lbl = tk.Label(frame, text=alarm_title, bg=bg, anchor="w")
            lbl.pack(side="left", fill="x", expand=True, padx=4)

            btn = tk.Button(frame, text="Detalhes", command=lambda t=alarm_title, d=alarm_desc: self.show_alarm_details(t, d))
            btn.pack(side="right", padx=4)

    def show_alarm_details(self, alarm_title, alarm_desc):
        """
        Desenha janela pop up com detalhes do alarme
        """
        messagebox.showinfo(f"Detalhes - {alarm_title}", alarm_desc)

    def on_close(self):
        """
        Desenha janela pop up com confirmação para fechar programa
        """
        if messagebox.askokcancel("Sair", "Deseja encerrar o Módulo 3?"):
            self.shutdown_event.set()
            self.root.quit()

    def add_medidas(self, id_: str, ts: datetime, medidas: [MedidasEletricas]):
        """
        Método auxiliar para adicionar novas medidas em self.series
        """
        if id_ not in self.series:
            self.series[id_] = {
                "tensao": { "A": [], "B": [], "C": [] },
                "corrente": { "A": [], "B": [], "C": [] },
                "potRealW": { "A": [], "B": [], "C": [] },
                "angTensao": { "A": [], "B": [], "C": [] },
                "potApaVA": { "A": [], "B": [], "C": [] },
                "potReatVAr": { "A": [], "B": [], "C": [] },
                "potRealW": { "A": [], "B": [], "C": [] },
                "fatorP": { "A": [], "B": [], "C": [] },
                "freq": { "A": [], "B": [], "C": [] },
            }
        for medida in medidas:
            medida = MedidasEletricas(**medida)
            self.series[id_]["tensao"][medida.fase].append((ts, medida.tensao))
            self.series[id_]["corrente"][medida.fase].append((ts, medida.corrente))
            self.series[id_]["potRealW"][medida.fase].append((ts, medida.potRealW))
            self.series[id_]["angTensao"][medida.fase].append((ts, medida.angTensao))
            self.series[id_]["potApaVA"][medida.fase].append((ts, medida.potApaVA))
            self.series[id_]["potReatVAr"][medida.fase].append((ts, medida.potReatVAr))
            self.series[id_]["potRealW"][medida.fase].append((ts, medida.potRealW))
            self.series[id_]["fatorP"][medida.fase].append((ts, medida.fatorP))
            self.series[id_]["freq"][medida.fase].append((ts, medida.freq))

# ----------------------------
# Main
# ----------------------------
def main():
    log.info("Módulo 3 iniciando (GUI)")

    # inicializa as variáveis de controle
    shutdown_event = threading.Event()
    seq_counter = itertools.count(1)

    # inicializa as filas
    priority_queue = queue.PriorityQueue()
    queue_gui = queue.Queue()
    queue_db = queue.Queue()

    # inicializa o socket UDP
    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        recv_sock.bind((BIND_ADDRESS, PORT))
        log.info("Socket bindado em %s:%d", BIND_ADDRESS, PORT)
    except Exception as e:
        log.exception("Falha bind socket: %s", e)
        return

    # inicializa as threads
    t_recv = threading.Thread(target=thread_recepcao, args=(recv_sock, priority_queue, shutdown_event, seq_counter), daemon=True, name="recv")
    t_proc = threading.Thread(target=thread_processamento, args=(priority_queue, queue_gui, queue_db, shutdown_event), daemon=True, name="proc")
    t_db = threading.Thread(target=thread_armazenamento, args=(queue_db, shutdown_event), daemon=True, name="db")

    for t in (t_recv, t_proc, t_db):
        log.info("Iniciando thread %s", t.name)
        t.start()

    # Inicia interface gráfica
    root = tk.Tk()
    app = Modulo3GUI(root, queue_gui, shutdown_event)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        log.info("KeyboardInterrupt recebido no mainloop")
    finally:
        log.info("Solicitando shutdown...")
        shutdown_event.set()
        time.sleep(0.3)
        try:
            recv_sock.close()
        except Exception:
            pass
        log.info("Finalizado.")

if __name__ == "__main__":
    main()

