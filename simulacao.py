import threading
import subprocess

PYTHON = "python"
SCRIPTS = ["modulo1.py","modulo2.py","modulo4.py","modulo5.py",]

def run_script(script: str):
    subprocess.call([PYTHON, script])

if __name__ == "__main__":
    threads = []
    for script in SCRIPTS:
        thread = threading.Thread(target=run_script, args=(script,))
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()
    
